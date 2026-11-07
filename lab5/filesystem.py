from models import FileSystemError, Inode, OpenFile


class FileSystem:
    MAX_SYMLINKS = 40

    def __init__(self, block_size: int = 128, max_name_bytes: int = 32):
        if block_size <= 0 or max_name_bytes <= 0:
            raise ValueError("Розмір блоку та максимальна довжина імені мають бути додатними")
        self.block_size = block_size
        self.max_name_bytes = max_name_bytes
        self.mkfs(16)

    def mkfs(self, inode_count: int) -> None:
        if inode_count < 2:
            raise FileSystemError("Потрібно щонайменше 2 inode: корінь і звичайний файл")
        self.inodes: list[Inode | None] = [None] * inode_count
        self.inodes[0] = Inode(kind="dir", nlink=2, entries={".": 0, "..": 0})
        self.cwd = 0
        self.open_files: dict[int, OpenFile] = {}

    def _check_name(self, name: str) -> None:
        if (not name or name in (".", "..") or "/" in name or "\0" in name
                or len(name.encode("utf-8")) > self.max_name_bytes):
            raise FileSystemError("Недопустиме ім'я файлу")

    def _allocate(self, inode: Inode) -> int:
        for number in range(1, len(self.inodes)):
            if self.inodes[number] is None:
                self.inodes[number] = inode
                return number
        raise FileSystemError("Немає вільних inode")

    def _lookup(self, pathname: str, follow_final: bool = True) -> int:
        if not pathname or "\0" in pathname:
            raise FileSystemError("Недопустимий шлях")

        current = 0 if pathname.startswith("/") else self.cwd
        parts = [part for part in pathname.split("/") if part]
        must_be_dir = pathname.endswith("/")
        hops = 0

        while parts:
            component = parts.pop(0)
            directory = self.inodes[current]
            if directory is None or directory.kind != "dir" or directory.removed:
                raise FileSystemError("Компонент шляху не є доступною директорією")
            if component not in directory.entries:
                raise FileSystemError(f"Не знайдено компонент шляху: {component!r}")

            next_number = directory.entries[component]
            next_inode = self.inodes[next_number]
            assert next_inode is not None
            if next_inode.kind == "sym" and (parts or follow_final or must_be_dir):
                hops += 1
                if hops > self.MAX_SYMLINKS:
                    raise FileSystemError("Забагато переходів за символічними посиланнями")
                target = next_inode.target
                if not parts and target.endswith("/"):
                    must_be_dir = True
                parts = [part for part in target.split("/") if part] + parts
                current = 0 if target.startswith("/") else current
            else:
                current = next_number

        inode = self.inodes[current]
        assert inode is not None
        if must_be_dir and inode.kind != "dir":
            raise FileSystemError("Шлях із / у кінці має вказувати на директорію")
        return current

    def _parent(self, pathname: str, allow_trailing: bool = False) -> tuple[int, str]:
        if not pathname or "\0" in pathname:
            raise FileSystemError("Недопустимий шлях")
        if pathname.endswith("/") and not allow_trailing:
            raise FileSystemError("Шлях до цього об'єкта не має закінчуватися на /")
        parts = [part for part in pathname.split("/") if part]
        if not parts:
            raise FileSystemError("Кореневу директорію змінювати не можна")
        name = parts.pop()
        self._check_name(name)
        if parts:
            parent_path = ("/" if pathname.startswith("/") else "") + "/".join(parts)
            parent_number = self._lookup(parent_path)
        else:
            parent_number = 0 if pathname.startswith("/") else self.cwd
        parent = self.inodes[parent_number]
        if parent is None or parent.kind != "dir" or parent.removed:
            raise FileSystemError("Батьківська директорія не існує")
        return parent_number, name

    def _opened(self, fd: int) -> tuple[OpenFile, Inode]:
        entry = self.open_files.get(fd)
        if entry is None:
            raise FileSystemError(f"Неправильний або закритий fd: {fd}")
        inode = self.inodes[entry.inode_number]
        assert inode is not None and inode.kind == "reg"
        return entry, inode

    def _maybe_release(self, inode_number: int) -> None:
        inode = self.inodes[inode_number]
        assert inode is not None
        if inode.nlink == 0 and inode.open_count == 0:
            self.inodes[inode_number] = None

    def create(self, pathname: str) -> int:
        parent_number, filename = self._parent(pathname)
        parent = self.inodes[parent_number]
        assert parent is not None
        if filename in parent.entries:
            raise FileSystemError("Таке ім'я вже існує")
        number = self._allocate(Inode(kind="reg", nlink=1))
        parent.entries[filename] = number
        return number
    
    def rm(self, pathname: str, recursive: bool = False) -> None:
        parent_number, name = self._parent(pathname, allow_trailing=True)
        parent = self.inodes[parent_number]
        assert parent is not None

        number = parent.entries.get(name)
        if number is None:
            raise FileSystemError("Файл або директорію не знайдено")

        inode = self.inodes[number]
        assert inode is not None

        if pathname.endswith("/") and inode.kind != "dir":
            raise FileSystemError("Це не директорія")

        if inode.kind != "dir":
            self.unlink(pathname)
            return

        if not recursive:
            raise FileSystemError(
                "Це директорія. Використайте rm -r"
            )

        for child_name in list(inode.entries):

            if child_name in (".", ".."):
                continue

            child_path = pathname.rstrip("/") + "/" + child_name

            self.rm(child_path, recursive=True)

        self.rmdir(pathname)

    def mkdir(self, pathname: str) -> int:
        parent_number, name = self._parent(pathname, allow_trailing=True)
        parent = self.inodes[parent_number]
        assert parent is not None
        if name in parent.entries:
            raise FileSystemError("Таке ім'я вже існує")
        number = self._allocate(Inode(kind="dir", nlink=2,
                                      entries={".": -1, "..": parent_number}))
        self.inodes[number].entries["."] = number
        parent.entries[name] = number
        parent.nlink += 1  
        return number

    def rmdir(self, pathname: str) -> None:
        parent_number, name = self._parent(pathname, allow_trailing=True)
        parent = self.inodes[parent_number]
        assert parent is not None
        number = parent.entries.get(name)
        if number is None:
            raise FileSystemError("Директорію не знайдено")
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind != "dir":
            raise FileSystemError("Це не директорія")
        if set(inode.entries) != {".", ".."}:
            raise FileSystemError("Директорія не порожня")
        del parent.entries[name]
        parent.nlink -= 1
        if number == self.cwd:
            inode.entries.clear()
            inode.nlink = 0
            inode.removed = True  
        else:
            self.inodes[number] = None

    def cd(self, pathname: str) -> None:
        number = self._lookup(pathname)
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind != "dir":
            raise FileSystemError("Це не директорія")
        previous = self.cwd
        self.cwd = number
        old_inode = self.inodes[previous]
        if previous != number and old_inode is not None and old_inode.removed:
            self.inodes[previous] = None

    def pwd(self) -> str:
        if self.cwd == 0:
            return "/"
        parts = []
        current = self.cwd
        while current != 0:
            inode = self.inodes[current]
            assert inode is not None and inode.kind == "dir"
            parent_number = inode.entries[".."]
            parent = self.inodes[parent_number]
            assert parent is not None and parent.kind == "dir"
            for name, number in parent.entries.items():
                if number == current and name not in (".", ".."):
                    parts.append(name)
                    break
            current = parent_number
        return "/" + "/".join(reversed(parts))

    def symlink(self, target: str, pathname: str) -> int:
        if (not target or "\0" in target
                or len(target.encode("utf-8")) > self.block_size):
            raise FileSystemError("Вміст symlink має містити 1..B байтів")
        parent_number, name = self._parent(pathname)
        parent = self.inodes[parent_number]
        assert parent is not None
        if name in parent.entries:
            raise FileSystemError("Таке ім'я вже існує")
        number = self._allocate(Inode(kind="sym", nlink=1,
                                      size=len(target.encode("utf-8")), target=target))
        parent.entries[name] = number
        return number

    def stat(self, pathname: str) -> dict:
        number = self._lookup(pathname, follow_final=False)
        inode = self.inodes[number]
        assert inode is not None
        result = {
            "inode": number,
            "type": inode.kind,
            "nlink": inode.nlink,
            "size": inode.size,
            "nblock": len(inode.blocks),
            "blocks": sorted(inode.blocks),
            "open_count": inode.open_count,
        }
        if inode.kind == "sym":
            result["target"] = inode.target
        return result

    def ls(self, pathname: str | None = None) -> list[tuple[str, int]]:
        number = self.cwd if pathname is None else self._lookup(pathname)
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind != "dir" or inode.removed:
            raise FileSystemError("Це не доступна директорія")
        return sorted(inode.entries.items())

    def link(self, existing: str, new_pathname: str) -> None:
        number = self._lookup(existing, follow_final=False)
        parent_number, filename = self._parent(new_pathname)
        parent = self.inodes[parent_number]
        assert parent is not None
        if filename in parent.entries:
            raise FileSystemError("Нове ім'я вже існує")
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind == "dir":
            raise FileSystemError("Жорсткі посилання на директорії заборонені")
        parent.entries[filename] = number
        inode.nlink += 1

    def unlink(self, pathname: str) -> None:
        parent_number, filename = self._parent(pathname)
        parent = self.inodes[parent_number]
        assert parent is not None
        number = parent.entries.get(filename)
        if number is None:
            raise FileSystemError("Файл не знайдено")
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind == "dir":
            raise FileSystemError("Для директорій використовуйте rmdir")
        del parent.entries[filename]
        inode.nlink -= 1
        self._maybe_release(number)

    def open(self, pathname: str) -> int:
        number = self._lookup(pathname)
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind != "reg":
            raise FileSystemError("Відкривати можна тільки звичайні файли")
        fd = 0
        while fd in self.open_files:
            fd += 1
        self.open_files[fd] = OpenFile(inode_number=number)
        inode.open_count += 1
        return fd

    def close(self, fd: int) -> None:
        entry, inode = self._opened(fd)
        inode.open_count -= 1
        del self.open_files[fd]
        self._maybe_release(entry.inode_number)

    def seek(self, fd: int, offset: int) -> None:
        entry, _ = self._opened(fd)
        if offset < 0:
            raise FileSystemError("Зміщення не може бути від'ємним")
        entry.offset = offset

    def read(self, fd: int, size: int) -> bytes:
        entry, inode = self._opened(fd)
        if size < 0:
            raise FileSystemError("Кількість байтів не може бути від'ємною")
        end = min(entry.offset + size, inode.size)
        if end <= entry.offset:
            return b""  
        result = bytearray()
        position = entry.offset
        while position < end:
            block_no, in_block = divmod(position, self.block_size)
            count = min(end - position, self.block_size - in_block)
            block = inode.blocks.get(block_no)
            result.extend(block[in_block:in_block + count] if block is not None
                          else bytes(count))
            position += count
        entry.offset = end
        return bytes(result)

    def write(self, fd: int, data: bytes) -> int:
        entry, inode = self._opened(fd)
        if not isinstance(data, bytes):
            raise FileSystemError("write() очікує саме bytes")
        if not data:
            return 0  
        position = entry.offset
        written = 0
        while written < len(data):
            block_no, in_block = divmod(position, self.block_size)
            count = min(len(data) - written, self.block_size - in_block)
            fragment = data[written:written + count]
            block = inode.blocks.get(block_no)
            if block is None and any(fragment):
                block = bytearray(self.block_size)
                inode.blocks[block_no] = block
            if block is not None:
                block[in_block:in_block + count] = fragment
                if not any(block):
                    del inode.blocks[block_no]
            written += count
            position += count
        entry.offset = position
        inode.size = max(inode.size, position)
        return written

    def truncate(self, pathname: str, new_size: int) -> None:
        if new_size < 0:
            raise FileSystemError("Розмір файлу не може бути від'ємним")
        number = self._lookup(pathname)
        inode = self.inodes[number]
        assert inode is not None
        if inode.kind != "reg":
            raise FileSystemError("truncate дозволено тільки для звичайних файлів")
        if new_size < inode.size:
            for block_no in list(inode.blocks):
                if block_no * self.block_size >= new_size:
                    del inode.blocks[block_no]
            block_no, remainder = divmod(new_size, self.block_size)
            if remainder and block_no in inode.blocks:
                block = inode.blocks[block_no]
                block[remainder:] = bytes(self.block_size - remainder)
                if not any(block):
                    del inode.blocks[block_no]
        inode.size = new_size
    
    def tree(self, pathname: str = ".") -> dict[str, list]:
        number = self._lookup(pathname)
        inode = self.inodes[number]

        if inode is None or inode.kind != "dir" or inode.removed:
            raise FileSystemError("Це не доступна директорія")

        def build(number: int) -> list:
            directory = self.inodes[number]
            assert directory is not None and directory.kind == "dir"

            children = []

            for name, child_number in sorted(directory.entries.items()):
                if name in (".", ".."):
                    continue

                child = self.inodes[child_number]
                assert child is not None

                if child.kind == "dir":
                    children.append({name: build(child_number)})
                elif child.kind == "sym":
                    children.append(f"{name} -> {child.target}")
                else:
                    children.append(name)

            return children

        root_name = "/" if number == 0 else pathname.rstrip("/").split("/")[-1]
        return {root_name: build(number)}
    
    def tree_text(self, pathname: str = ".") -> str:
        tree = self.tree(pathname)

        root_name, children = next(iter(tree.items()))

        lines = [root_name if root_name == "/" else root_name + "/"]

        def render(items: list, prefix: str) -> None:
            for index, item in enumerate(items):
                is_last = index == len(items) - 1

                branch = "└── " if is_last else "├── "

                if isinstance(item, dict):
                    name, children = next(iter(item.items()))

                    lines.append(prefix + branch + name + "/")

                    new_prefix = prefix + ("    " if is_last else "│   ")

                    render(children, new_prefix)

                else:
                    lines.append(prefix + branch + item)

        render(children, "")

        return "\n".join(lines)

