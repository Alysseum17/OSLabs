import shlex

from filesystem import FileSystem
from models import FileSystemError


def shell() -> None:
    fs = FileSystem()
    print("Навчальна ФС №5. help — команди, exit — вихід")
    while True:
        try:
            parts = shlex.split(input("fs> "))
            if not parts:
                continue
            command, *args = parts
            if command in ("exit", "quit"):
                break
            if command == "help":
                print("mkfs N | mkdir PATH | rmdir PATH | cd PATH | symlink TARGET PATH | pwd")
                print("create PATH | stat PATH | ls [PATH] | open PATH | close FD | rm PATH | rm -r PATH | tree [PATH]")
                print("seek FD OFFSET | read FD SIZE | write FD SIZE")
                print("link OLD NEW | unlink PATH | truncate PATH SIZE | exit")
            elif command == "mkfs" and len(args) == 1:
                fs.mkfs(int(args[0]))
                print("ФС ініціалізовано")
            elif command == "mkdir" and len(args) == 1:
                print("inode =", fs.mkdir(args[0]))
            elif command == "rmdir" and len(args) == 1:
                fs.rmdir(args[0])
                print("Директорію видалено")
            elif command == "cd" and len(args) == 1:
                fs.cd(args[0])
                print("CWD inode =", fs.cwd)
            elif command == "pwd" and len(args) == 0:
                print("CWD =", fs.pwd())
            elif command == "symlink" and len(args) == 2:
                print("inode =", fs.symlink(args[0], args[1]))
            elif command == "create" and len(args) == 1:
                print("inode =", fs.create(args[0]))
            elif command == "rm":
                if len(args) == 1 and args[0] != "-r":
                    fs.rm(args[0])
                elif len(args) == 2 and args[0] == "-r":
                    fs.rm(args[1], recursive=True) 
                else:
                    raise FileSystemError("Використання: rm PATH або rm -r PATH")
                print("Видалено")
            elif command == "stat" and len(args) == 1:
                print(fs.stat(args[0]))
            elif command == "ls" and len(args) <= 1:
                for name, number in fs.ls(args[0] if args else None):
                    inode = fs.inodes[number]
                    assert inode is not None
                    extra = f" -> {inode.target}" if inode.kind == "sym" else ""
                    print(f"{name} => {inode.kind}, inode={number}{extra}")
            elif command == "open" and len(args) == 1:
                print("fd =", fs.open(args[0]))
            elif command == "close" and len(args) == 1:
                fs.close(int(args[0]))
                print("Закрито")
            elif command == "seek" and len(args) == 2:
                fs.seek(int(args[0]), int(args[1]))
                print("Зміщення встановлено")
            elif command == "read" and len(args) == 2:
                data = fs.read(int(args[0]), int(args[1]))
                print(f"Прочитано {len(data)} байтів: {data!r}")
            elif command == "write" and len(args) == 2:
                count = int(args[1])
                if count < 0:
                    raise FileSystemError("Розмір запису має бути невід'ємним")
                data = input("data> ").encode("utf-8")
                if len(data) != count:
                    raise FileSystemError(f"Потрібно {count} байтів, введено {len(data)}")
                print("Записано байтів:", fs.write(int(args[0]), data))
            elif command == "link" and len(args) == 2:
                fs.link(args[0], args[1])
                print("Посилання створено")
            elif command == "unlink" and len(args) == 1:
                fs.unlink(args[0])
                print("Посилання видалено")
            elif command == "truncate" and len(args) == 2:
                fs.truncate(args[0], int(args[1]))
                print("Розмір змінено")
            elif command == "tree" and len(args) <= 1:
                print(fs.tree_text(args[0] if args else "."))
            else:
                print("Невідома команда або кількість аргументів. Спробуйте help")
        except (FileSystemError, ValueError) as error:
            print("Помилка:", error)
        except (EOFError, KeyboardInterrupt):
            print()
            break