import unittest

from filesystem import FileSystem
from models import FileSystemError


class FileSystemTests(unittest.TestCase):
    def setUp(self):
        self.fs = FileSystem(block_size=8)
        self.fs.mkfs(4)  

    def test_create_and_ls_and_stat(self):
        self.assertEqual(self.fs.create("a"), 1)
        self.assertEqual(self.fs.create("b"), 2)
        self.assertEqual(self.fs.ls(), [("a", 1), ("b", 2)])
        self.assertEqual(self.fs.stat("a")["nlink"], 1)
        with self.assertRaises(FileSystemError):
            self.fs.create("a")

    def test_write_read_and_block_boundary(self):
        self.fs.create("a")
        fd = self.fs.open("a")
        self.assertEqual(self.fs.write(fd, b"abcdefghijk"), 11)
        self.assertEqual(self.fs.stat("a")["nblock"], 2)
        self.fs.seek(fd, 6)
        self.assertEqual(self.fs.read(fd, 5), b"ghijk")
        self.assertEqual(self.fs.read(fd, 10), b"")  # EOF

    def test_separate_offsets_and_fd_reuse(self):
        self.fs.create("a")
        f0 = self.fs.open("a")
        f1 = self.fs.open("a")
        self.assertEqual((f0, f1), (0, 1))
        self.fs.write(f0, b"1234")
        self.assertEqual(self.fs.read(f1, 2), b"12")
        self.assertEqual(self.fs.read(f0, 2), b"")
        self.fs.close(f0)
        self.assertEqual(self.fs.open("a"), 0)

    def test_hard_links_and_release_after_last_close(self):
        self.fs.create("a")
        fd = self.fs.open("a")
        self.fs.write(fd, b"data")
        self.fs.link("a", "b")
        self.assertEqual(self.fs.stat("b")["nlink"], 2)
        self.fs.unlink("a")
        self.assertEqual(self.fs.stat("b")["nlink"], 1)
        self.fs.unlink("b")
        self.assertEqual(self.fs.ls(), [])
        self.fs.seek(fd, 0)
        self.assertEqual(self.fs.read(fd, 4), b"data")
        self.assertIsNotNone(self.fs.inodes[1])
        self.fs.close(fd)
        self.assertIsNone(self.fs.inodes[1])
        self.assertEqual(self.fs.create("c"), 1)

    def test_sparse_truncate_and_seek_beyond_eof(self):
        self.fs.create("a")
        self.fs.truncate("a", 1_000_000)
        self.assertEqual(self.fs.stat("a")["nblock"], 0)
        fd = self.fs.open("a")
        self.fs.seek(fd, 999_998)
        self.fs.write(fd, b"XY")
        self.assertEqual(self.fs.stat("a")["nblock"], 1)
        self.fs.seek(fd, 999_994)
        self.assertEqual(self.fs.read(fd, 8), b"\0\0\0\0XY")  # EOF

    def test_truncate_shrink_erases_tail_and_reextend_zeros(self):
        self.fs.create("a")
        fd = self.fs.open("a")
        self.fs.write(fd, b"ABCDEFGH123456")
        self.fs.truncate("a", 3)
        self.assertEqual(self.fs.stat("a")["nblock"], 1)
        self.fs.truncate("a", 16)
        self.fs.seek(fd, 0)
        self.assertEqual(self.fs.read(fd, 16), b"ABC" + b"\0" * 13)
        self.assertEqual(self.fs.stat("a")["nblock"], 1)

    def test_zero_only_writes_no_allocation_and_zero_reclaims(self):
        self.fs.create("a")
        fd = self.fs.open("a")
        self.fs.write(fd, bytes(16))
        self.assertEqual(self.fs.stat("a")["nblock"], 0)
        self.fs.seek(fd, 2)
        self.fs.write(fd, b"X")
        self.assertEqual(self.fs.stat("a")["nblock"], 1)
        self.fs.seek(fd, 2)
        self.fs.write(fd, b"\0")
        self.assertEqual(self.fs.stat("a")["nblock"], 0)

    def test_inode_capacity_and_invalid_inputs(self):
        for name in ("a", "b", "c"):
            self.fs.create(name)
        with self.assertRaises(FileSystemError):
            self.fs.create("d")
        with self.assertRaises(FileSystemError):
            self.fs.create("bad/name")
        with self.assertRaises(FileSystemError):
            self.fs.open("missing")
        with self.assertRaises(FileSystemError):
            self.fs.close(0)
        fd = self.fs.open("a")
        with self.assertRaises(FileSystemError):
            self.fs.seek(fd, -1)
        with self.assertRaises(FileSystemError):
            self.fs.read(fd, -1)
        with self.assertRaises(FileSystemError):
            self.fs.write(fd, "not bytes")
        with self.assertRaises(FileSystemError):
            self.fs.truncate("a", -1)

    def test_empty_write_does_not_extend_file(self):
        self.fs.create("a")
        fd = self.fs.open("a")
        self.fs.seek(fd, 100)
        self.assertEqual(self.fs.write(fd, b""), 0)
        self.assertEqual(self.fs.stat("a")["size"], 0)

    def test_unlinked_file_occupies_inode_until_closed(self):
        self.fs.create("a")
        self.fs.create("b")
        self.fs.create("c")
        fd = self.fs.open("a")
        self.fs.unlink("a")
        with self.assertRaises(FileSystemError):
            self.fs.create("d")
        self.fs.close(fd)
        self.assertEqual(self.fs.create("d"), 1)


if __name__ == "__main__":
    unittest.main()
