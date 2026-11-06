import shlex

from filesystem import FileSystem
from models import FileSystemError


def shell() -> None:
    fs = FileSystem()
    print("Навчальна ФС. help — команди, exit — вихід")
    while True:
        try:
            parts = shlex.split(input("fs> "))
            if not parts:
                continue
            command, *args = parts
            if command in ("exit", "quit"):
                break
            if command == "help":
                print("mkfs N | create NAME | stat NAME | ls | open NAME | close FD")
                print("seek FD OFFSET | read FD SIZE | write FD SIZE | link OLD NEW")
                print("unlink NAME | truncate NAME SIZE | exit")
            elif command == "mkfs" and len(args) == 1:
                fs.mkfs(int(args[0]))
                print("ФС ініціалізовано")
            elif command == "create" and len(args) == 1:
                print("inode =", fs.create(args[0]))
            elif command == "stat" and len(args) == 1:
                print(fs.stat(args[0]))
            elif command == "ls" and not args:
                for name, number in fs.ls():
                    print(f"{name} => reg, inode={number}")
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
            else:
                print("Невідома команда або кількість аргументів. Спробуйте help")
        except (FileSystemError, ValueError) as error:
            print("Помилка:", error)
        except (EOFError, KeyboardInterrupt):
            print()
            break
