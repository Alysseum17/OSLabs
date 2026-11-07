from dataclasses import dataclass, field


class FileSystemError(ValueError):
    pass

@dataclass
class Inode:
    kind: str  
    nlink: int = 0
    size: int = 0
    blocks: dict[int, bytearray] = field(default_factory=dict)
    open_count: int = 0
    entries: dict[str, int] = field(default_factory=dict)  
    target: str = ""  
    removed: bool = False 

@dataclass
class OpenFile:
    inode_number: int
    offset: int = 0