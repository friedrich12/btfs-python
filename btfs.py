import libtorrent as lt
import os, stat, errno, time, sys
# pull in some spaghetti to make this stuff work without fuse-py being installed
try:
    import _find_fuse_parts
except ImportError:
    pass
import fuse
from fuse import Fuse


session = None 
handle = None

files = {}
dirs = {}

if not hasattr(fuse, '__version__'):
    raise RuntimeError("your fuse-py doesn't know of fuse.__version__, probably it's too old.")

fuse.fuse_python_api = (0, 2)

hello_path = '/hello'
hello_str = b'Hello World!\n'

#TODO: Update this later
time_of_mount = 0

def is_dir(path):
    if dirs.has_key(path):
        return True
    else:
        return False

def is_file(path):
    if files.has_key(path):
        return True
    else:
        return False

def is_root(path):
    return path == "/"

class MyStat(fuse.Stat):
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0

class HelloFS(Fuse):

    def getattr(self, path):
        st = MyStat()

        if(not is_dir(path) and not is_file(path) and not is_root(path)):
            return -errno.ENOENT
        
        st.st_uid = os.getuid()
        st.st_gid = os.getgid()
        st.st_mtime = time_of_mount

        if(is_root(path) or is_dir(path)):
            st_mode = stat.S_IFDIR | 0o755
        else:
            ti = handle.torrent_file()
       
            file_size = ti.file_at(files[path]).size
            progress = []
            handle.file_progress(progress,libtorrent.torrent_handle.piece_granularity);
            stbuf->st_blocks = progress[files[path]] / 512
            stbuf->st_mode = S_IFREG | 0o444
            stbuf->st_size = file_size

        return st

    def readdir(self, path, buf, offset):
        if (not is_dir(path) and not is_file(path) and not is_root(path)):
            return -errno.ENOENT

        if (is_file(path)):
            return -errno.ENOTDIR

        for r in  '.', '..', buf[1:]:
            yield fuse.Direntry(r)

        for i in path:
            yield fuse.Direntry(r)

        return st

    
    def open(self, path):            
        if (not is_dir(path) and not is_file(path)):
            return -errno.ENOENT    
                        
        if (is_dir(path)):
            return -EISDIR
                                                             
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES                                         
                                          
    def read(self, path, buf, size, offset): 
        if (not is_dir(path) and not is_file(path)):
            return -errno.ENOENT
                     
        if (is_dir(path)):
            return -errno.EISDIR  
                                      
                                                        
        # Read *r = new Read(buf, files[path], offset, size);
                                  
        # reads.push_back(r);
                                    
        # Wait for read to finish             
        # int s = r->read();                    
                       
        # reads.remove(r);
                                 
        # delete r;                                            
                                                                    
        # return s; 

def main():
    usage="""
Userspace hello example
""" + Fuse.fusage
    server = HelloFS(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
