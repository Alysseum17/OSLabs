from filesystem import FileSystem
from models import FileSystemError


def demo() -> None:
    fs = FileSystem()
    fs.mkfs(16)
    print("CWD =", fs.pwd())
    print("mkdir /docs ->", fs.mkdir("/docs"))
    print("mkdir /docs/projects ->", fs.mkdir("/docs/projects"))
    print("stat /docs ->", fs.stat("/docs"))
    fs.cd("/docs/projects")
    print("CWD =", fs.pwd())
    print("cd /docs/projects; create note.txt ->", fs.create("note.txt"))
    fd = fs.open("note.txt")
    fs.write(fd, b"Hello")
    fs.seek(fd, 0)
    print("read note.txt ->", fs.read(fd, 5))
    fs.truncate("note.txt", 32)
    print("truncate note.txt 32 ->", fs.stat("note.txt"))
    print("read zero-filled area ->", fs.read(fd, 4))
    fs.link("note.txt", "second_name.txt")
    print("link note.txt second_name.txt ->", fs.stat("note.txt"))
    fs.unlink("second_name.txt")
    fs.close(fd)
    print("symlink projects/note.txt /docs/shortcut ->",
          fs.symlink("projects/note.txt", "/docs/shortcut"))
    print("open /docs/shortcut ->", fs.open("/docs/shortcut"))
    print("stat /docs/shortcut ->", fs.stat("/docs/shortcut"))
    print("link /docs/shortcut /docs/second ->", fs.link("/docs/shortcut", "/docs/second"))
    print("stat /docs/second ->", fs.stat("/docs/second"))
    print("ls /docs ->", fs.ls("/docs"))
    fs.symlink("/loop_b", "/loop_a")
    fs.symlink("/loop_a", "/loop_b")
    try:
        fs.open("/loop_a")
    except FileSystemError as error:
        print("Цикл symlink ->", error)
    fs.unlink("/docs/shortcut")
    fs.unlink("/docs/second")
    print("ls /docs after unlink symlinks ->", fs.ls("/docs"))
    fs.close(0)
    fs.unlink("/docs/projects/note.txt")
    fs.cd("/")
    fs.rmdir("/docs/projects")
    print("rmdir /docs/projects -> OK")
    print("stat /docs ->", fs.stat("/docs"))
    print("\n--- Перевірка rm та rm -r ---")
    fs.mkdir("/tmp")
    fs.mkdir("/tmp/sub")
    fs.create("/tmp/a.txt")
    fs.create("/tmp/sub/b.txt")
    fs.symlink("/docs", "/tmp/docs_link")
    print("ls /tmp до видалення ->", fs.ls("/tmp"))

    fs.rm("/tmp/a.txt")
    print("rm /tmp/a.txt; ls /tmp ->", fs.ls("/tmp"))

    try:
        fs.rm("/tmp")
    except FileSystemError as error:
        print("rm /tmp без -r ->", error)

    fs.rm("/tmp", recursive=True)
    print("rm -r /tmp; ls / ->", fs.ls("/"))
    print("/docs після rm -r /tmp ->", fs.stat("/docs"))

    print("\n--- Демонстрація tree ---")
    fs.mkdir("/examples")
    fs.mkdir("/examples/nested")
    fs.create("/examples/note.txt")
    fs.create("/examples/nested/lab.py")
    fs.symlink("/docs", "/examples/shortcut")

    print("tree /examples ->\n" + fs.tree_text("/examples"))
    print("tree / ->\n" + fs.tree_text("/"))
