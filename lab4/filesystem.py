from models import FileSystemError, Inode, OpenFile


class FileSystem:
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
        self.inodes[0] = Inode(kind="dir", nlink=1)
        self.directory: dict[str, int] = {}
        self.open_files: dict[int, OpenFile] = {}

    def _check_name(self, name: str) -> None:
        if (not name or name in (".", "..") or "/" in name or "\0" in name
                or len(name.encode("utf-8")) > self.max_name_bytes):
            raise FileSystemError("Недопустиме ім'я файлу")

    def _inode_number(self, name: str) -> int:
        try:
            return self.directory[name]
        except KeyError:
            raise FileSystemError(f"Файл {name!r} не знайдено") from None

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

    def create(self, name: str) -> int:
        self._check_name(name)
        if name in self.directory:
            raise FileSystemError("Таке ім'я вже існує")
        for number in range(1, len(self.inodes)):
            if self.inodes[number] is None:
                self.inodes[number] = Inode(kind="reg", nlink=1)
                self.directory[name] = number
                return number
        raise FileSystemError("Немає вільних дескрипторів файлів у ФС (inode)")

    def stat(self, name: str) -> dict:
        number = self._inode_number(name)
        inode = self.inodes[number]
        assert inode is not None
        return {
            "inode": number,
            "type": inode.kind,
            "nlink": inode.nlink,
            "size": inode.size,
            "nblock": len(inode.blocks),
            "blocks": sorted(inode.blocks),
            "open_count": inode.open_count,
        }

    def ls(self) -> list[tuple[str, int]]:
        return sorted(self.directory.items())

    def link(self, existing: str, new_name: str) -> None:
        number = self._inode_number(existing)
        self._check_name(new_name)
        if new_name in self.directory:
            raise FileSystemError("Нове ім'я вже існує")
        inode = self.inodes[number]
        assert inode is not None
        self.directory[new_name] = number
        inode.nlink += 1

    def unlink(self, name: str) -> None:
        number = self._inode_number(name)
        del self.directory[name]
        inode = self.inodes[number]
        assert inode is not None
        inode.nlink -= 1
        self._maybe_release(number)

    def open(self, name: str) -> int:
        number = self._inode_number(name)
        fd = 0
        while fd in self.open_files:
            fd += 1
        self.open_files[fd] = OpenFile(inode_number=number)
        inode = self.inodes[number]
        assert inode is not None
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

    def truncate(self, name: str, new_size: int) -> None:
        if new_size < 0:
            raise FileSystemError("Розмір файлу не може бути від'ємним")
        number = self._inode_number(name)
        inode = self.inodes[number]
        assert inode is not None
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
