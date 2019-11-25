#
#

import sys
import tempfile
import os
import errno
import pytest

import xattr
from xattr import NS_USER, XATTR_CREATE, XATTR_REPLACE

NAMESPACE = os.environ.get("NAMESPACE", NS_USER)

if sys.hexversion >= 0x03000000:
    PY3K = True
    EMPTY_NS = bytes()
else:
    PY3K = False
    EMPTY_NS = ''

TEST_DIR = os.environ.get("TEST_DIR", ".")
TEST_IGNORE_XATTRS = os.environ.get("TEST_IGNORE_XATTRS", "")
if TEST_IGNORE_XATTRS == "":
    TEST_IGNORE_XATTRS = []
else:
    TEST_IGNORE_XATTRS = TEST_IGNORE_XATTRS.split(",")
    # The following has to be a list comprehension, not a generator, to
    # avoid weird consequences of lazy evaluation.
    TEST_IGNORE_XATTRS.extend([a.encode() for a in TEST_IGNORE_XATTRS])

USER_NN = "test"
USER_ATTR = NAMESPACE.decode() + "." + USER_NN
USER_VAL = "abc"
EMPTY_VAL = ""
LARGE_VAL = "x" * 2048
MANYOPS_COUNT = 131072

if PY3K:
    USER_NN = USER_NN.encode()
    USER_VAL = USER_VAL.encode()
    USER_ATTR = USER_ATTR.encode()
    EMPTY_VAL = EMPTY_VAL.encode()
    LARGE_VAL = LARGE_VAL.encode()

# Helper functions

def ignore_tuples(attrs):
    """Remove ignored attributes from the output of xattr.get_all."""
    return [attr for attr in attrs
            if attr[0] not in TEST_IGNORE_XATTRS]

def ignore(attrs):
    """Remove ignored attributes from the output of xattr.list"""
    return [attr for attr in attrs
            if attr not in TEST_IGNORE_XATTRS]

def lists_equal(attrs, value):
    """Helper to check list equivalence, skipping TEST_IGNORE_XATTRS."""
    assert ignore(attrs) == value

def tuples_equal(attrs, value):
    """Helper to check list equivalence, skipping TEST_IGNORE_XATTRS."""
    assert ignore_tuples(attrs) == value

# Fixtures and helpers

@pytest.fixture
def testdir():
    """per-test temp dir based in TEST_DIR"""
    with tempfile.TemporaryDirectory(dir=TEST_DIR) as dname:
        yield dname

def get_file(path):
    fh, fname = tempfile.mkstemp(".test", "xattr-", path)
    return fh, fname

def get_file_name(path):
    fh, fname = get_file(path)
    os.close(fh)
    return fname

def get_file_fd(path):
    return get_file(path)[0]

def get_file_object(path):
    fd = get_file(path)[0]
    return os.fdopen(fd)

def get_dir(path):
    return tempfile.mkdtemp(".test", "xattr-", path)

def get_symlink(path, dangling=True):
    """create a symlink"""
    fh, fname = get_file(path)
    os.close(fh)
    if dangling:
        os.unlink(fname)
    sname = fname + ".symlink"
    os.symlink(fname, sname)
    return fname, sname

def get_valid_symlink(path):
    return get_symlink(path, dangling=False)[1]

def get_dangling_symlink(path):
    return get_symlink(path, dangling=True)[1]

# Note: user attributes are only allowed on files and directories, so
# we have to skip the symlinks here. See xattr(7).
ITEMS_P = [
    (get_file_name, False),
    (get_file_fd, False),
    (get_file_object, False),
    (get_dir, False),
    (get_valid_symlink, False),
#    (get_valid_symlink, True),
#    (get_dangling_symlink, True),
]

ITEMS_D = [
    "file name",
    "file FD",
    "file object",
    "directory",
    "file via symlink",
#    "valid symlink",
#    "dangling symlink",
]

@pytest.fixture(params=ITEMS_P, ids=ITEMS_D)
def subject(testdir, request):
    return request.param[0](testdir), request.param[1]

@pytest.fixture(params=[True, False], ids=["with namespace", "no namespace"])
def use_ns(request):
    return request.param

@pytest.fixture(params=[True, False], ids=["dangling", "valid"])
def use_dangling(request):
    return request.param

### Test functions

def test_empty_value(subject):
    item, nofollow = subject
    xattr.set(item, USER_ATTR, EMPTY_VAL, nofollow=nofollow)
    assert xattr.get(item, USER_ATTR, nofollow=nofollow) == EMPTY_VAL

def test_large_value(subject):
    item, nofollow = subject
    xattr.set(item, USER_ATTR, LARGE_VAL)
    assert xattr.get(item, USER_ATTR, nofollow=nofollow) == LARGE_VAL


def test_file_mixed_access_deprecated(testdir):
    """test mixed access to file (deprecated functions)"""
    fh, fname = get_file(testdir)
    with os.fdopen(fh) as fo:
        lists_equal(xattr.listxattr(fname), [])
        xattr.setxattr(fname, USER_ATTR, USER_VAL)
        lists_equal(xattr.listxattr(fh), [USER_ATTR])
        assert xattr.getxattr(fo, USER_ATTR) == USER_VAL
        tuples_equal(xattr.get_all(fo), [(USER_ATTR, USER_VAL)])
        tuples_equal(xattr.get_all(fname),
                     [(USER_ATTR, USER_VAL)])

def test_file_mixed_access(testdir):
    """test mixed access to file"""
    fh, fname = get_file(testdir)
    with os.fdopen(fh) as fo:
        lists_equal(xattr.list(fname), [])
        xattr.set(fname, USER_ATTR, USER_VAL)
        lists_equal(xattr.list(fh), [USER_ATTR])
        assert xattr.list(fh, namespace=NAMESPACE) == [USER_NN]
        assert xattr.get(fo, USER_ATTR) == USER_VAL
        assert xattr.get(fo, USER_NN, namespace=NAMESPACE) == USER_VAL
        tuples_equal(xattr.get_all(fo),
                     [(USER_ATTR, USER_VAL)])
        assert xattr.get_all(fo, namespace=NAMESPACE) == \
            [(USER_NN, USER_VAL)]
        tuples_equal(xattr.get_all(fname), [(USER_ATTR, USER_VAL)])
        assert xattr.get_all(fname, namespace=NAMESPACE) == \
            [(USER_NN, USER_VAL)]

def test_ListSetGet(subject, use_ns):
    """check list, set, get operations against an item"""
    item = subject[0]
    lists_equal(xattr.list(item), [])
    with pytest.raises(EnvironmentError):
        if use_ns:
            xattr.set(item, USER_NN, USER_VAL, flags=XATTR_REPLACE,
                      namespace=NAMESPACE)
        else:
            xattr.set(item, USER_ATTR, USER_VAL, flags=XATTR_REPLACE)
    if use_ns:
        xattr.set(item, USER_NN, USER_VAL,
                  namespace=NAMESPACE)
    else:
        xattr.set(item, USER_ATTR, USER_VAL)
    with pytest.raises(EnvironmentError):
        if use_ns:
            xattr.set(item, USER_NN, USER_VAL,
                      flags=XATTR_CREATE, namespace=NAMESPACE)
        else:
            xattr.set(item, USER_ATTR, USER_VAL, flags=XATTR_CREATE)
    if use_ns:
        assert xattr.list(item, namespace=NAMESPACE) == [USER_NN]
    else:
        lists_equal(xattr.list(item), [USER_ATTR])
        lists_equal(xattr.list(item, namespace=EMPTY_NS),
                    [USER_ATTR])
    if use_ns:
        assert xattr.get(item, USER_NN, namespace=NAMESPACE) == USER_VAL
    else:
        assert xattr.get(item, USER_ATTR) == USER_VAL
    if use_ns:
        assert xattr.get_all(item, namespace=NAMESPACE) == \
            [(USER_NN, USER_VAL)]
    else:
        tuples_equal(xattr.get_all(item),
                     [(USER_ATTR, USER_VAL)])
    if use_ns:
        xattr.remove(item, USER_NN, namespace=NAMESPACE)
    else:
        xattr.remove(item, USER_ATTR)
    lists_equal(xattr.list(item), [])
    tuples_equal(xattr.get_all(item), [])
    with pytest.raises(EnvironmentError):
        if use_ns:
            xattr.remove(item, USER_NN, namespace=NAMESPACE)
        else:
            xattr.remove(item, USER_ATTR)

def test_ListSetGetDeprecated(subject):
    """check deprecated list, set, get operations against an item"""
    item = subject[0]
    lists_equal(xattr.listxattr(item), [])
    with pytest.raises(EnvironmentError):
        xattr.setxattr(item, USER_ATTR, USER_VAL, XATTR_REPLACE)
    xattr.setxattr(item, USER_ATTR, USER_VAL, 0)
    with pytest.raises(EnvironmentError):
        xattr.setxattr(item, USER_ATTR, USER_VAL, XATTR_CREATE)
    lists_equal(xattr.listxattr(item), [USER_ATTR])
    assert xattr.getxattr(item, USER_ATTR) == USER_VAL
    tuples_equal(xattr.get_all(item), [(USER_ATTR, USER_VAL)])
    xattr.removexattr(item, USER_ATTR)
    lists_equal(xattr.listxattr(item), [])
    tuples_equal(xattr.get_all(item), [])
    with pytest.raises(EnvironmentError):
        xattr.removexattr(item, USER_ATTR)

def test_many_ops(subject):
    """test many ops"""
    item = subject[0]
    xattr.set(item, USER_ATTR, USER_VAL)
    VL = [USER_ATTR]
    VN = [USER_NN]
    for i in range(MANYOPS_COUNT):
        lists_equal(xattr.list(item), VL)
        lists_equal(xattr.list(item, namespace=EMPTY_NS), VL)
        assert xattr.list(item, namespace=NAMESPACE) == VN
    for i in range(MANYOPS_COUNT):
        assert xattr.get(item, USER_ATTR) == USER_VAL
        assert xattr.get(item, USER_NN, namespace=NAMESPACE) == USER_VAL
    for i in range(MANYOPS_COUNT):
        tuples_equal(xattr.get_all(item),
                     [(USER_ATTR, USER_VAL)])
        assert xattr.get_all(item, namespace=NAMESPACE) == \
            [(USER_NN, USER_VAL)]

def test_many_ops_deprecated(subject):
    """test many ops (deprecated functions)"""
    item = subject[0]
    xattr.setxattr(item, USER_ATTR, USER_VAL)
    VL = [USER_ATTR]
    for i in range(MANYOPS_COUNT):
        lists_equal(xattr.listxattr(item), VL)
    for i in range(MANYOPS_COUNT):
        assert xattr.getxattr(item, USER_ATTR) == USER_VAL
    for i in range(MANYOPS_COUNT):
        tuples_equal(xattr.get_all(item),
                     [(USER_ATTR, USER_VAL)])

def test_no_attributes_deprecated(subject):
    """test no attributes (deprecated functions)"""
    item = subject[0]
    lists_equal(xattr.listxattr(item), [])
    tuples_equal(xattr.get_all(item), [])
    with pytest.raises(EnvironmentError):
        xattr.getxattr(item, USER_ATTR)

def test_no_attributes_deprecated_symlinks(testdir, use_dangling):
    """test no attributes on symlinks (deprecated functions)"""
    _, sname = get_symlink(testdir, dangling=use_dangling)
    lists_equal(xattr.listxattr(sname, True), [])
    tuples_equal(xattr.get_all(sname, nofollow=True), [])
    with pytest.raises(EnvironmentError):
        xattr.getxattr(sname, USER_ATTR, True)

def test_no_attributes(subject):
    """test no attributes"""
    item = subject[0]
    lists_equal(xattr.list(item), [])
    assert xattr.list(item, namespace=NAMESPACE) == []
    tuples_equal(xattr.get_all(item), [])
    assert xattr.get_all(item, namespace=NAMESPACE) == []
    with pytest.raises(EnvironmentError):
        xattr.get(item, USER_NN, namespace=NAMESPACE)

def test_no_attributes_symlinks(testdir, use_dangling):
    """test no attributes on symlinks"""
    _, sname = get_symlink(testdir, dangling=use_dangling)
    lists_equal(xattr.list(sname, nofollow=True), [])
    assert xattr.list(sname, nofollow=True,
                      namespace=NAMESPACE) == []
    tuples_equal(xattr.get_all(sname, nofollow=True), [])
    assert xattr.get_all(sname, nofollow=True,
                         namespace=NAMESPACE) == []
    with pytest.raises(EnvironmentError):
        xattr.get(sname, USER_NN, namespace=NAMESPACE, nofollow=True)

def test_binary_payload_deprecated(subject):
    """test binary values (deprecated functions)"""
    item = subject[0]
    BINVAL = b"abc\0def"
    xattr.setxattr(item, USER_ATTR, BINVAL)
    lists_equal(xattr.listxattr(item), [USER_ATTR])
    assert xattr.getxattr(item, USER_ATTR) == BINVAL
    tuples_equal(xattr.get_all(item), [(USER_ATTR, BINVAL)])
    xattr.removexattr(item, USER_ATTR)

def test_binary_payload(subject):
    """test binary values"""
    item = subject[0]
    BINVAL = b"abc\0def"
    xattr.set(item, USER_ATTR, BINVAL)
    lists_equal(xattr.list(item), [USER_ATTR])
    assert xattr.list(item, namespace=NAMESPACE) == [USER_NN]
    assert xattr.get(item, USER_ATTR) == BINVAL
    assert xattr.get(item, USER_NN, namespace=NAMESPACE) == BINVAL
    tuples_equal(xattr.get_all(item), [(USER_ATTR, BINVAL)])
    assert xattr.get_all(item, namespace=NAMESPACE) == [(USER_NN, BINVAL)]
    xattr.remove(item, USER_ATTR)

def test_none_namespace(subject):
    with pytest.raises(TypeError):
        xattr.get(subject[0], USER_ATTR, namespace=None)

@pytest.mark.parametrize(
    "call",
    [xattr.get, xattr.list, xattr.listxattr,
     xattr.remove, xattr.removexattr,
     xattr.set, xattr.setxattr,
     xattr.get, xattr.getxattr])
def test_wrong_call(call):
    with pytest.raises(TypeError):
        call()

@pytest.mark.parametrize(
    "call, args", [(xattr.get, [USER_ATTR]),
                   (xattr.listxattr, []),
                   (xattr.list, []),
                   (xattr.remove, [USER_ATTR]),
                   (xattr.removexattr, [USER_ATTR]),
                   (xattr.get, [USER_ATTR]),
                   (xattr.getxattr, [USER_ATTR]),
                   (xattr.set, [USER_ATTR, USER_VAL]),
                   (xattr.setxattr, [USER_ATTR, USER_VAL])])
def test_wrong_argument_type(call, args):
    with pytest.raises(TypeError):
        call(object(), *args)
