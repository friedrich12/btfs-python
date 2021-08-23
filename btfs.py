import libtorrent
import tempfile
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
handle = None


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

class Read:
    buf = None
    index = None
    offset = None
    size = None
    failed = False
    parts = []

    def __init__(self, b, idx , off, sz):
        self.buf = b
        self.index = idx
        self.offset = off
        self.size = sz
        
        ti = handle.torrent_file() 

        file_size = ti.file_at(index).size;

        while size > 0 and offset < file_size:
            part = ti.map_file(index, offset, size)
            part.length = min(ti.piece_size(part.piece) - part.start, part.length)
            
            parts.append(Part(part, buf))
            self.size -= part.length;
            self.offset += part.length;
            self.buf += part.length
    
    def fail(piece):
        for x in parts:
            if x.part.piece == piece and not x.filled:
                    self.failed = True
    
    #TODO: Check me later
    def copy(piece, buffer, size):
        for x in parts:
            if x.part.piece == piece and not x.filled:
                i.filled = buf[0:i.part.length] = buffer[i.part.start:]

    def trigger():
        for x in parts:
            if handle.have_piece(x.part.piece):
                handle.read_piece(x.part.piece)

    def finished():
        for x in parts:
            if not i.filled:
                return False
        return True;

    def size():
        s = 0
        for x in parts:
            s += x.part.length
        return s;

    def read():
        if self.size() <= 0:
            return 0

        # Trigger reads of finished pieces
        self.trigger()

        # Move sliding window to first piece to serve this request
        self.jump(parts.front().part.piece, size())

        if failed:
            return -errno.EIO
        else:
            return self.size()

class HelloFS(Fuse):
    def statfs(path, stbuf):

        if not handle.is_valid():
            return -errno.ENOENT

        st = handle.status();

        if not st.has_metadata:
            return -errno.ENOENT

        ti = handle.torrent_file()

        stbuf.f_bsize = 4096
        stbuf.f_frsize = 512
        stbuf.f_blocks =  (ti.total_size() / 512)
        stbuf.f_bfree =  ((ti.total_size() - st.total_done) / 512)
        stbuf.f_bavail =  ((ti.total_size() - st.total_done) / 512)
        stbuf.f_files =  (files.size() + dirs.size());
        stbuf.f_ffree = 0;


    def init(conn):

        time_of_mount = None

        p = fuse_get_context().private_data

        flags = libtorrent.session.add_default_plugins | libtorrent.session.start_default_features

        alerts = libtorrent.alert.tracker_notification | libtorrent.alert.stats_notification | libtorrent.alert.storage_notification | libtorrent.alert.progress_notification | libtorrent.alert.status_notification | libtorrent.alert.error_notification | libtorrent.alert.dht_notification | libtorrent.alert.peer_notification

        session = libtorrent.session(
		    libtorrent.fingerprint(
			    "LT",
			    LIBTORRENT_VERSION_MAJOR,
			    LIBTORRENT_VERSION_MINOR,
			    0,
			    0),
		    (params.min_port, params.max_port),
		    "0.0.0.0",
		    flags,
		    alerts)

        se = session.settings()

        se.request_timeout = 10
        se.strict_end_game_mode = False
        se.announce_to_all_trackers = True
        se.announce_to_all_tiers = True
        se.enable_incoming_tcp = not params.utp_only
        se.enable_outgoing_tcp = not params.utp_only
        se.download_rate_limit = params.max_download_rate * 1024
        se.upload_rate_limit = params.max_upload_rate * 1024
    
        session.set_settings(se)
        session.add_dht_router(("router.bittorrent.com", 6881))
        session.add_dht_router(("router.utorrent.com", 6881))
        session.add_dht_router(("dht.transmissionbt.com", 6881))
        session.async_add_torrent(p)

        pack.set_int(pack.request_timeout, 10)
        pack.set_str(pack.listen_interfaces, interfaces.str())
        pack.set_bool(pack.strict_end_game_mode, false)
        pack.set_bool(pack.announce_to_all_trackers, true)
        pack.set_bool(pack.announce_to_all_tiers, true)
        pack.set_bool(pack.enable_incoming_tcp, not params.utp_only)
        pack.set_bool(pack.enable_outgoing_tcp, not params.utp_only)
        pack.set_int(pack.download_rate_limit, params.max_download_rate * 1024)
        pack.set_int(pack.upload_rate_limit, params.max_upload_rate * 1024)
        pack.set_int(pack.alert_mask, alerts)

        session = libtorrent.session(pack, flags)

        session.add_torrent(p)



    def destroy(user_data):
        flags = 0

        if not params.keep:
            flags |= libtorrent.session.delete_files

        session.remove_torrent(handle, flags)

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
            stbuf.st_blocks = progress[files[path]] / 512
            stbuf.st_mode = S_IFREG | 0o444
            stbuf.st_size = file_size

        return st
    
    def listxattr(path, data, len):
        xattrs = None;               
        xattrslen = 0;      
 
        if (is_root(path)):           
            xattrs = XATTR_IS_BTFS + "\0" + XATTR_IS_BTFS_ROOT
        elif (is_dir(path)):               
            xattrs = XATTR_IS_BTFS
        elif (is_file(path)):                                  
            xattrs = XATTR_IS_BTFS + "\0" + XATTR_FILE_INDEX
        else:                     
            return -errno.ENOENT
                          
        xattrslen = len(xttrs)
        # The minimum required length
        if len == 0:                                                 
            return xattrslen
                             
        if len < xattrslen:        
            return -ERANGE;                  
                                       
        data[:xattrslen] = xattrs

        return xattrslen

    def getxattr(path, key, value, len):
        position = 0
        xattr = [None] * 16
        xattrlen = 0

        k = str(key)

        if is_file(path) and k == XATTR_FILE_INDEX:
            xattrlen = snprintf(xattr, sizeof (xattr), "%d", files[path])
        elif is_root(path) and k == XATTR_IS_BTFS_ROOT:
            xattrlen = 0
        elif k == XATTR_IS_BTFS:
            xattrlen = 0
        else:
            return -errno.ENODATA

        # The minimum required length
        if len == 0:
            return xattrlen

        if position >= xattrlen:
            return 0

        if len <  xattrlen - position:
            return -errno.ERANGE

        
        value[:xattrlen - position] = xattr[position:]
        
        return xattrlen -  position



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
                                      
                                                        
        r = Read(buf, files[path], offset, size)
                                  
        reads.append(r)
                                    
        # Wait for read to finish             
        s = r.read()                    
                       
        reads.remove(r);
                                 
        return s

def handle_read_piece_alert(a):
    if a.ec:
        print(a.message())
        for x in reads:
            x.fail(a.piece)
    else:
        for x in reads:
            x.copy(a.piece, a.buffer.get(), a.size())

def handle_piece_finished_alert(a):
    #printf("%s: %d\n", __func__, static_cast<int>(a->piece_index));

    for x in reads:
        x.trigger()

    # Advance sliding window
    advance()

def handle_torrent_added_alert(a):
    handle = a.handle

    if a.handle.status().has_metadata:
        setup()

def handle_metadata_received_alert(a):
    handle = a.handle
    setup()

def handle_alert(a):
    if a.type == libtorrent.read_piece_alert.alert_type:
        handle_read_piece_alert(a)
    elif a.type == libtorrent.piece_finished_alert.alert_type:
        handle_piece_finished_alert(a)
    elif a.type == libtorrent.metadata_received_alert.alert_type:
        handle_metadata_received_alert(a)
    elif a.type == libtorrent.torrent_added_alert.alert_type:
        handle_torrent_added_alert(a)
    elif a.type == libtorrent.dht_bootstrap_alert.alert_type:
        # Force DHT announce because libtorrent won't by itself
        handle.force_dht_announce()
    else:
        print(a.message())

def setup():
    print("Got metadata. Now ready to start downloading.\n")

    ti = handle.torrent_file()

    if params.browse_only:
        handle.pause()

    for i in range(0,ti.num_files()):
        parent = ""
        p = str(ti.file_at(i).path.c_str())

        if not p:
            continue

        arr = p.split('/')
        for x in arr:
            if len(x) <= 0:
                continue

            if parent.length() <= 0:
                # Root dir <-> children mapping
                dirs["/"] = x
            else:
                # Non-root dir <-> children mapping
                dirs[parent] = x

                parent += "/"
                parent += x

                # Path <-> file index mapping
                files["/" + ti.file_at(i).path] = i

#def alert_queue_loop_destroy(data):
    #Log *log = (Log *) data;
    #if (log):
    #    delete log

def alert_queue_loop(data):
    while True:
        if not session.wait_for_alert(libtorrent.seconds(1)):
            continue

        alerts = []
        session.pop_alerts(alerts)

        for x in alerts:
            handle_alert(x)


def populate_target(arg):
    templ = str()

    if arg:
        templ += arg;
    elif os.getenv("XDG_DATA_HOME"):
        templ += os.getenv("XDG_DATA_HOME")
        templ += "/btfs";
    elif (os.getenv("HOME")):
        templ += os.getenv("HOME")
        templ += "/btfs"
    else:
        templ += "/tmp/btfs"

    try:
        os.mkdir(str(templ), stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
    except OSError as error:
        pass

    templ += "/btfs-XXXXXX"


    try:
        os.mkdir(templ)
        x = os.path.realpath(templ)
        print(x)
    except OSError as error:
        pass

    print(templ)
    return templ

def handle_http(contents, size, nmemb, userp):
    output = userp

    # Offset into buffer to write to
    off = output.size

    output.expand(nmemb * size)

    output.buf[off:nmeb*size] = contents

    # Must return number of bytes copied
    return nmemb * size

def populate_metadata(p, arg):
    uri = str(arg)

    if uri.find("http:") == 0 or uri.find("https:") == 0:
        output = []
        c = pycurl.Curl()
        c.setopt(c.URL, uri)
        c.setopt(c.WRITEFUNCTION, handle_http)
        c.setopt(c.WRITEDATA, output)
        c.setopt(c.USERAGENT, "btfs/" + VERSION)
        c.setopt(c.POSTFIELDS, '@request.json')
        c.setopt(c.CURLOPT_FOLLOWLOCATION, 1)
        c.perform()
        c.close()

        ec = None 

        p.ti = libtorrent.torrent_info(output.buf, output.size, ec)

        if ec:
            if params.browse_only:
                p.flags |= libtorrent.add_torrent_params.flag_paused
        elif uri.find("magnet:") == 0:
            ec = None
            parse_magnet_uri(uri, p, ec)
            if ec:
                print("Failed to parse magnet\n")
            else:
                r = os.path.realpath(uri.c_str())

                if not r:
                    print("Find metadata failed")
                ec = None
                p.ti = libtorrent.torrent_info(r, ec)

                if ec:
                    print("Parse metadata failed: %s\n")

                if params.browse_only:
                    p.flags |= libtorrent.add_torrent_params.flag_paused
    return True

def main():
    params.min_port = 6881            
    params.max_port = 6889
    usage="""
BTFS
""" + Fuse.fusage
    server = HelloFS(version="%prog " + fuse.__version__,
                     usage=usage,
                dash_s_do='setsingle')

    target =populate_target(params.data_directory)

    p = libtorrent.add_torrent_params()
    p.flags &= ~libtorrent.torrent_flags.auto_managed
    p.flags &= ~libtorrent.torrent_flags.paused

    p.save_path = target + "/files"

    try:
        os.mkdir(p.save_path, 0o777)
    except OSError as error:
        pass

    populate_metadata(p, params.metadata)
    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
