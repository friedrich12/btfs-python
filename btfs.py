import libtorrent
import tempfile
from threading import *
from stat import *
import os, stat, errno, time, sys
# pull in some spaghetti to make this stuff work without fuse-py being installed
try:
    import _find_fuse_parts
except ImportError:
    pass
import fuse
import pycurl
from io import StringIO
from fuse import Fuse

session = None
reads = []
save_path = str()
handle = libtorrent.torrent_handle()
info = None
cursor = int()
import logging

logging.basicConfig(filename='app.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')
logging.warning('This will get logged to a file')

class btfs_params:
    version = None
    browse_only = None
    keep = None
    utp_only = None
    data_directory = None
    min_port = None
    max_port = None
    max_download_rate = None
    max_upload_rate = None
    metadata = None

XATTR_FILE_INDEX = "user.btfs.file_index"
XATTR_IS_BTFS_ROOT = "user.btfs.is_btfs_root"
XATTR_IS_BTFS = "user.btfs.is_btfs"

params = btfs_params()
p = libtorrent.add_torrent_params()
files = {}
dirs = {}

if not hasattr(fuse, '__version__'):
    raise RuntimeError("your fuse-py doesn't know of fuse.__version__, probably it's too old.")

fuse.fuse_python_api = (0, 2)

hello_path = '/hello'
hello_str = b'Hello World!\n'

temp = int()

def move_to_next_unfinished(piece, num_pieces):
    global handle
    global temp


    for i in range(0, num_pieces):
        if not handle.have_piece(piece +i):
            temp = piece
            return True
    temp = piece
    return False

def jump(piece, size):
    global handle
    global temp

    tail = piece
    ti = info

    if not move_to_next_unfinished(tail, ti.num_pieces()):
        return

    tail = temp

    cursor = tail

    for i in range(0, 16):
        handle.piece_priority(tail, 7)
        tail+=1


def advance():
    jump(cursor, 0)

#TODO: Update this later
time_of_mount = 0

def is_dir(path):
    global dirs

    if path in dirs:
        return True
    else:
        return False

def is_file(path):
    global files

    if path in files:
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

class Part:
    buf = str()
    filled = False
    part = libtorrent.peer_request()

    def __init__(self, p, buf):
       self.part = libtorrent.peer_request(p)
       self.buf = str(buf)
       self.filled = False

class Read:
    buf = str()
    index = None
    offset = None
    size = None
    failed = False
    parts = []

    def __init__(self, idx , off, sz):
        global handle
        
        self.index = idx
        self.offset = off
        self.size = sz
        
        ti = handle.torrent_file() 

        file_size = ti.file_at(self.index).size;

        while size > 0 and offset < file_size:
            part = ti.map_file(index, offset, size)
            part.length = min(ti.piece_size(part.piece) - part.start, part.length)
            
            self.parts.append(Part(part, buf))
            
            self.size -= part.length;
            self.offset += part.length;
            #self.buf += part.length
    
    def fail(piece):
        for x in self.parts:
            if x.part.piece == piece and not x.filled:
                    self.failed = True
    
    #TODO: Check me later
    def copy(piece, buffer, size):
        for x in self.parts:
            if x.part.piece == piece and not x.filled:
                self.buf[0:x.part.length] = buffer[x.part.start:]
                #if(len(self.buf[0:x.part.length] != 0):
                x.filled = True

    def trigger():
        global handle

        for x in self.parts:
            if handle.have_piece(x.part.piece):
                handle.read_piece(x.part.piece)

    def finished():
        for x in self.parts:
            if not x.filled:
                return False
        return True;

    def size():
        s = 0
        for x in self.parts:
            s += x.part.length
        return s;

    def read():
        if self.size() <= 0:
            return 0

        # Trigger reads of finished pieces
        self.trigger()

        # Move sliding window to first piece to serve this request
        jump(parts.front().part.piece, self.size())

        if failed:
            return -errno.EIO
        else:
            return self.size()

def alert_queue_loop():
    global session
    while True:
        session.wait_for_alert(5)
        alerts = session.pop_alerts()

        for x in alerts:
            handle_alert(x)
        time.sleep(5)

def start_torrent():
    global handle
    global save_path
    global session
    global info
    info = libtorrent.torrent_info("sample.torrent")
    print("USING SAVE PATH: " + save_path)
    handle = session.add_torrent({'ti': info , 'save_path': str(save_path)})

    while not handle.is_seed():
        s = handle.status()
        time.sleep(5)
    logging.warning("READ TO GO!!")

class HelloFS(Fuse):
    def statfs(self):
        global handle

        if not handle.is_valid():
            return -errno.ENOENT

        st = handle.status();

        if not st.has_metadata:
            return -errno.ENOENT

        ti = handle.torrent_file()
        
        stbuf = os.statvfs()

        stbuf.f_bsize = 4096
        stbuf.f_frsize = 512
        stbuf.f_blocks =  (ti.total_size() / 512)
        stbuf.f_bfree =  ((ti.total_size() - st.total_done) / 512)
        stbuf.f_bavail =  ((ti.total_size() - st.total_done) / 512)
        stbuf.f_files =  (files.size() + dirs.size());
        stbuf.f_ffree = 0;
        
        return stbuf

    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        global info
        global handle
        global session
        global save_path
        
        time_of_mount = None

        #flags = libtorrent.session_flags_t.add_default_plugins | libtorrent.session_flags_t.start_default_features

        #alerts = libtorrent.alert.category_t.tracker_notification | libtorrent.alert.category_t.stats_notification | libtorrent.alert.category_t.storage_notification | libtorrent.alert.category_t.progress_notification | libtorrent.alert.category_t.status_notification | libtorrent.alert.category_t.error_notification | libtorrent.alert.category_t.dht_notification | libtorrent.alert.category_t.peer_notification


        settings = {
                'alert_mask': libtorrent.alert.category_t.all_categories,
                'enable_dht': False, 'enable_lsd': False, 'enable_natpmp': False,
                'enable_upnp': False, 'listen_interfaces': '0.0.0.0:0', 'file_pool_size': 1,
                'request_timeout': 10, 'strict_end_game_mode': False, 'announce_to_all_trackers': True,
                'announce_to_all_tiers': True, 'enable_incoming_tcp': not params.utp_only, 'enable_outgoing_tcp': not params.utp_only}
                #'download_rate_limit': params.max_download_rate * 1024, 'upload_rate_limit': params.max_upload_rate * 1024}

        session = libtorrent.session(settings)
        session.listen_on(6881, 6891)
        session.add_dht_router("router.bittorrent.com", 6881)
        session.add_dht_router("router.utorrent.com", 6881)
        session.add_dht_router("dht.transmissionbt.com", 6881)


        x = Thread(target=start_torrent)
        x.start()

        y = Thread(target=alert_queue_loop)
        y.start()

        time.sleep(10)

    def destroy(user_data):
        global session
        global handle

        flags = 0

        if not params.keep:
            flags |= libtorrent.session.delete_files

        session.remove_torrent(handle, flags)

    def getattr(self, path):
        global handle
        global save_path
        global info

        st = MyStat()

        if(not is_dir(path) and not is_file(path) and not is_root(path)):
            return -errno.ENOENT
        
        st.st_uid = os.getuid()
        st.st_gid = os.getgid()
        #st.st_mtime = time_of_mount

        if(is_root(path) or is_dir(path)):
            st.st_mode = stat.S_IFDIR | 0o755
        else:
            file_size = info.file_at(files[path]).size
            progress = handle.file_progress(libtorrent.torrent_handle.piece_granularity);
            st.st_blocks = progress[files[path]] / 512
            st.st_mode = stat.S_IFREG | 0o444
            st.st_size = file_size

        return st
    
    def readdir(self, path, offset):
        global dirs
        global save_path

        if (not is_dir(path) and not is_file(path) and not is_root(path)):
            return -errno.ENOENT

        if (is_file(path)):
            return -errno.ENOTDIR

        for d in dirs[path]:
            for r in d, save_path[1:]:
                yield fuse.Direntry(r)

    
    def open(self, path, flags):            
        if (not is_dir(path) and not is_file(path)):
            return -errno.ENOENT    
                        
        if (is_dir(path)):
            return -errno.EISDIR
                                                             
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES
                                          
    def read(self, path, size, offset): 
        global save_path
        global reads
        global files

        if (not is_dir(path) and not is_file(path)):
            return -errno.ENOENT
                     
        if (is_dir(path)):
            return -errno.EISDIR  
                                      
                                                        
        r = Read(files[path], offset, size)
                                  
        reads.append(r)
                                    
        r.read()                    
                       
        reads.remove(r);
                                 
        return r.buf

def handle_read_piece_alert(a):
    global reads
    if a.ec:
        print(a.message())
        for x in reads:
            x.fail(a.piece)
    else:
        for x in reads:
            x.copy(a.piece, a.buffer.get(), a.size())

def handle_piece_finished_alert(a):
    global reads
    #printf("%s: %d\n", __func__, static_cast<int>(a->piece_index));

    for x in reads:
        x.trigger()

    # Advance sliding window
    advance()

def handle_torrent_added_alert(a):
    global handle
    handle = a.handle

    if a.handle.status().has_metadata:
        setup()

def handle_metadata_received_alert(a):
    global handle
    handle = a.handle
    setup()

def handle_alert(a):
    global handle
    if isinstance(a,libtorrent.read_piece_alert):
        print(a.message())
        handle_read_piece_alert(a)
    elif isinstance(a,libtorrent.piece_finished_alert):
        print(a.message())
        handle_piece_finished_alert(a)
    elif isinstance(a, libtorrent.metadata_received_alert):
        print(a.message())
        handle_metadata_received_alert(a)
    elif isinstance(a, libtorrent.torrent_added_alert):
        print(a.message())
        handle_torrent_added_alert(a)
    elif isinstance(a, libtorrent.dht_bootstrap_alert):
        # Force DHT announce because libtorrent won't by itself
        print(a.message())
        handle.force_dht_announce()
    else:
        print(a.message())

def setup():
    global handle
    global files
    global dirs
    global info
    print("Got metadata. Now ready to start downloading.\n")

    print(handle)
    ti = info

    if params.browse_only:
        handle.pause()

    for i in range(0,ti.num_files()):
        parent = ""
        p = str(ti.file_at(i).path)

        if not p:
            continue

        arr = p.split('/')
        for x in arr:
            if len(x) <= 0:
                continue

            if len(parent) <= 0:
                # Root dir <-> children mapping
                if not "/" in dirs:
                    dirs["/"] = []
                dirs["/"].append(x)
            else:
                # Non-root dir <-> children mapping
                if not parent in dirs:
                    dirs[parent] = []
            
                dirs[parent].append(x)

            parent += "/"
            parent += x

        # Path <-> file index mapping
        files["/" + ti.file_at(i).path] = i
    print("I GOT THIS: ")
    print(dirs)
    print("I GOT THIS: ")
    print(files)

#def alert_queue_loop_destroy(data):
    #Log *log = (Log *) data;
    #if (log):
    #    delete log


def populate_target(arg):
    #templ = str()

    #if arg:
    #    templ += arg;
    #elif os.getenv("XDG_DATA_HOME"):
    #    templ += os.getenv("XDG_DATA_HOME")
    #    templ += "/btfs";
    #elif (os.getenv("HOME")):
    #    templ += os.getenv("HOME")
    #    templ += "/btfs"
    #else:
    #    templ += "/tmp/btfs"
    #
    #try:
    #    os.mkdir(str(templ))
    #except OSError as error:
    #    print("Failed to create directory")
    #    pass

    #templ += "/btfs-XXXXXX"

    templ = tempfile.mkdtemp()
    print("CREATE TEMP DIRECTORY AT: " + templ)
    
    return templ

def handle_http(contents, size, nmemb, userp):
    output = userp

    # Offset into buffer to write to
    off = output.size

    output.expand(nmemb * size)

    output.buf[off:nmeb*size] = contents

    # Must return number of bytes copied
    return nmemb * size

# Add support for magnet links
#def populate_metadata():
#    r = os.path.realpath("sample.torrent")
#    p.ti = libtorrent.torrent_info(r)

def main():
    global save_path
    params.min_port = 6881            
    params.max_port = 6889
    params.metadata = "sample.torrent"
    usage="""
BTFS
""" + Fuse.fusage

    target =populate_target(params.data_directory)

    #p = libtorrent.add_torrent_params()
    #p.flags &= ~libtorrent.torrent_flags.auto_managed
    #p.flags &= ~libtorrent.torrent_flags.paused

    save_path = target
    print("SAVE PATH IS " + save_path)

    try:
        os.mkdir(save_path, 0o777)
    except OSError as error:
        pass

    server = HelloFS(version="%prog " + fuse.__version__,
                     usage=usage,
                dash_s_do='setsingle')
    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
