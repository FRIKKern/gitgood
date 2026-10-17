/* Diagnostic prototype only. No production use or acceptance.
 * Eight finite filesystem roles: four metadata families and distinct complete
 * Root/private/service/kernel reads. Preserve ordered fresh observations,
 * predicates, buffering and tuple fields. No observation survives a call.
 * C API references:
 * https://docs.python.org/3.12/c-api/unicode.html#c.PyUnicode_EncodeFSDefault
 * https://docs.python.org/3.12/c-api/exceptions.html#c.PyErr_SetFromErrnoWithFilenameObject
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#define PY_SSIZE_T_CLEAN
#ifndef __linux__
#error "This diagnostic prototype is Linux-only"
#endif
#include <Python.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <limits.h>
#include <unistd.h>

static unsigned long long fingerprint_calls=0, plan_calls=0, custody_calls=0;
static unsigned long long read_calls=0, prepare_calls=0;

static int fresh_lstat(PyObject *name, struct stat *info)
{
    PyObject *encoded;
    int result, saved_errno;
    if (PyErr_CheckSignals() < 0) return -1;
    if (!PyUnicode_CheckExact(name)) {
        PyErr_SetString(PyExc_TypeError, "Probe requires exact path strings");
        return -1;
    }
    encoded = PyUnicode_EncodeFSDefault(name);
    if (encoded == NULL) return -1;
    if (memchr(PyBytes_AS_STRING(encoded), 0, (size_t)PyBytes_GET_SIZE(encoded)) != NULL) {
        Py_DECREF(encoded);
        PyErr_SetString(PyExc_ValueError, "embedded null byte");
        return -1;
    }
    for (;;) {
        result = lstat(PyBytes_AS_STRING(encoded), info);
        saved_errno = errno;
        if (result == 0 || saved_errno != EINTR) break;
        if (PyErr_CheckSignals() < 0) {
            Py_DECREF(encoded);
            return -1;
        }
    }
    Py_DECREF(encoded);
    if (result != 0) {
        errno = saved_errno;
        PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, name);
        return -1;
    }
    return 0;
}

static PyObject *nanoseconds(time_t seconds, long remainder)
{
    /* Python integer arithmetic preserves timestamps beyond int64 nanoseconds. */
    PyObject *whole = NULL, *billion = NULL, *fraction = NULL;
    PyObject *scaled = NULL, *result = NULL;
    whole = PyLong_FromLongLong((long long)seconds);
    billion = PyLong_FromLong(1000000000L);
    fraction = PyLong_FromLong(remainder);
    if (whole == NULL || billion == NULL || fraction == NULL) goto done;
    scaled = PyNumber_Multiply(whole, billion);
    if (scaled != NULL) result = PyNumber_Add(scaled, fraction);
done:
    Py_XDECREF(whole); Py_XDECREF(billion); Py_XDECREF(fraction); Py_XDECREF(scaled);
    return result;
}

static int put_unsigned(PyObject *tuple, Py_ssize_t index, unsigned long long value)
{
    PyObject *item = PyLong_FromUnsignedLongLong(value);
    if (item == NULL) return -1;
    PyTuple_SET_ITEM(tuple, index, item);
    return 0;
}

static PyObject *fingerprint(PyObject *self, PyObject *arguments)
{
    PyObject *name, *parents, *maximum_object, *executable_object;
    PyObject *parent_records = NULL, *leaf = NULL, *result = NULL, *item;
    long long maximum;
    Py_ssize_t count, index;
    int executable;
    struct stat info;
    (void)self;
    if (!PyArg_ParseTuple(arguments, "OOOO", &name, &parents, &maximum_object, &executable_object)) return NULL;
    if (!PyUnicode_CheckExact(name) || !PyTuple_CheckExact(parents) ||
        !PyLong_CheckExact(maximum_object) || !PyBool_Check(executable_object)) {
        PyErr_SetString(PyExc_TypeError, "Unsupported diagnostic probe input");
        return NULL;
    }
    maximum = PyLong_AsLongLong(maximum_object);
    if (maximum == -1 && PyErr_Occurred()) return NULL;
    count = PyTuple_GET_SIZE(parents);
    if (maximum <= 0 || count > 64) {
        PyErr_SetString(PyExc_ValueError, "Diagnostic probe bound exceeded");
        return NULL;
    }
    if (++fingerprint_calls > 10000000) {
        PyErr_SetString(PyExc_RuntimeError, "Metadata probe counter bound"); return NULL;
    }
    executable = executable_object == Py_True;
    parent_records = PyTuple_New(count);
    if (parent_records == NULL) return NULL;
    for (index = 0; index < count; ++index) {
        PyObject *parent = PyTuple_GET_ITEM(parents, index);
        if (fresh_lstat(parent, &info) < 0) goto done;
        if (!S_ISDIR(info.st_mode) || info.st_uid != 0 || (info.st_mode & 0022) != 0) {
            Py_DECREF(parent_records);
            Py_RETURN_NONE;
        }
        item = Py_BuildValue("(OKKkk)", parent,
            (unsigned long long)info.st_dev, (unsigned long long)info.st_ino,
            (unsigned long)info.st_uid, (unsigned long)info.st_mode);
        if (item == NULL) goto done;
        PyTuple_SET_ITEM(parent_records, index, item);
    }
    /* Encode/stat the leaf only after every preceding parent check passed. */
    if (fresh_lstat(name, &info) < 0) goto done;
    if (!S_ISREG(info.st_mode) || info.st_uid != 0 || info.st_nlink != 1 ||
        (info.st_mode & 0022) != 0 || info.st_size <= 0 || info.st_size > maximum ||
        (executable && (info.st_mode & 0111) == 0)) {
        Py_DECREF(parent_records);
        Py_RETURN_NONE;
    }
    leaf = PyTuple_New(8);
    if (leaf == NULL) goto done;
    if (put_unsigned(leaf, 0, (unsigned long long)info.st_dev) < 0 ||
        put_unsigned(leaf, 1, (unsigned long long)info.st_ino) < 0) goto done;
    item = PyLong_FromLongLong((long long)info.st_size);
    if (item == NULL) goto done;
    PyTuple_SET_ITEM(leaf, 2, item);
    item = nanoseconds(info.st_mtim.tv_sec, info.st_mtim.tv_nsec);
    if (item == NULL) goto done;
    PyTuple_SET_ITEM(leaf, 3, item);
    item = nanoseconds(info.st_ctim.tv_sec, info.st_ctim.tv_nsec);
    if (item == NULL) goto done;
    PyTuple_SET_ITEM(leaf, 4, item);
    if (put_unsigned(leaf, 5, (unsigned long long)info.st_uid) < 0 ||
        put_unsigned(leaf, 6, (unsigned long long)info.st_mode) < 0 ||
        put_unsigned(leaf, 7, (unsigned long long)info.st_nlink) < 0) goto done;
    result = PyTuple_Pack(2, leaf, parent_records);
done:
    Py_XDECREF(leaf);
    Py_XDECREF(parent_records);
    return result;
}


/* All tables are ephemeral arguments. No metadata or result is retained. */
static int u64(PyObject *v, unsigned long long *out) {
    if (!PyLong_CheckExact(v)) return 0;
    *out=PyLong_AsUnsignedLongLong(v);
    if (PyErr_Occurred()) { if (PyErr_ExceptionMatches(PyExc_OverflowError)) {PyErr_Clear();return 0;} return -1; }
    return 1;
}
static int i64(PyObject *v, long long *out) {
    if (!PyLong_CheckExact(v)) return 0;
    *out=PyLong_AsLongLong(v);
    if (PyErr_Occurred()) { if (PyErr_ExceptionMatches(PyExc_OverflowError)) {PyErr_Clear();return 0;} return -1; }
    return 1;
}
static int strings(PyObject *v, int optional) {
    Py_ssize_t i;
    if (optional && v==Py_None) return 1;
    if (!PyList_CheckExact(v) || PyList_GET_SIZE(v)>1024) return 0;
    for(i=0;i<PyList_GET_SIZE(v);i++) if(!PyUnicode_CheckExact(PyList_GET_ITEM(v,i)))return 0;
    return 1;
}
static int row(PyObject *v,const char *spec) {
    Py_ssize_t i,n=(Py_ssize_t)strlen(spec); unsigned long long u;long long s;
    if(!PyTuple_CheckExact(v)||PyTuple_GET_SIZE(v)!=n)return 0;
    for(i=0;i<n;i++) {
        PyObject *x=PyTuple_GET_ITEM(v,i);int r=1;
        switch(spec[i]) {
        case 's':r=PyUnicode_CheckExact(x)&&PyUnicode_GET_LENGTH(x)<=8192;break;
        case 'u':r=u64(x,&u);break;
        case 'n':r=i64(x,&s);break;
        case 'b':r=PyBool_Check(x);break;
        case 't':r=PyTuple_CheckExact(x);break;
        case 'O':break;
        case 'L':r=strings(x,1);break;
        case 'z':r=(x==Py_None)?1:u64(x,&u);if(r>0&&x!=Py_None&&u>INT_MAX)r=0;break;
        default:return 0;
        }
        if(r<=0)return r;
    }
    return 1;
}
static int rows(PyObject *v,const char *spec,Py_ssize_t limit) {
    Py_ssize_t i;int r;
    if(!PyTuple_CheckExact(v)||PyTuple_GET_SIZE(v)>limit)return 0;
    for(i=0;i<PyTuple_GET_SIZE(v);i++){r=row(PyTuple_GET_ITEM(v,i),spec);if(r<=0)return r;}
    return 1;
}
static int fresh_fd(int fd,struct stat *info) {
    int r,saved;
    if(PyErr_CheckSignals()<0)return -1;
    do {r=fstat(fd,info);saved=errno;if(r<0&&saved==EINTR&&PyErr_CheckSignals()<0)return -1;}while(r<0&&saved==EINTR);
    if(r<0){errno=saved;PyErr_SetFromErrno(PyExc_OSError);return -1;}return 0;
}
static int fresh_at(PyObject *name,int fd,struct stat *info) {
    PyObject *raw;int r,saved;
    if(PyErr_CheckSignals()<0)return -1;
    raw=PyUnicode_EncodeFSDefault(name);if(!raw)return -1;
    if(memchr(PyBytes_AS_STRING(raw),0,(size_t)PyBytes_GET_SIZE(raw))){Py_DECREF(raw);PyErr_SetString(PyExc_ValueError,"embedded null byte");return -1;}
    do {r=fstatat(fd,PyBytes_AS_STRING(raw),info,AT_SYMLINK_NOFOLLOW);saved=errno;
        if(r<0&&saved==EINTR&&PyErr_CheckSignals()<0){Py_DECREF(raw);return -1;}}while(r<0&&saved==EINTR);
    Py_DECREF(raw);if(r<0){errno=saved;PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError,name);return -1;}return 0;
}
static int timestamp_equal(struct timespec value,PyObject *expected) {
    long long ns=PyLong_AsLongLong(expected),seconds,remainder;
    if(PyErr_Occurred())return -1;
    seconds=ns/1000000000LL;remainder=ns%1000000000LL;
    if(remainder<0){seconds--;remainder+=1000000000LL;}
    return (long long)value.tv_sec==seconds && value.tv_nsec==remainder;
}
static int equal_meta(struct stat *s,PyObject *v,int directory) {
    unsigned long long values[6];Py_ssize_t i,count=directory?5:6;int r;
    values[0]=(unsigned long long)s->st_dev;values[1]=(unsigned long long)s->st_ino;
    values[2]=(unsigned long long)s->st_uid;values[3]=(unsigned long long)s->st_gid;
    values[4]=(unsigned long long)s->st_mode;values[5]=(unsigned long long)s->st_nlink;
    for(i=0;i<count;i++)if(PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,i))!=values[i])return 0;
    if(!directory && PyLong_AsLongLong(PyTuple_GET_ITEM(v,6))!=(long long)s->st_size)return 0;
    if(PyErr_Occurred())return -1;
    r=timestamp_equal(s->st_mtim,PyTuple_GET_ITEM(v,directory?5:7));if(r<=0)return r;
    return timestamp_equal(s->st_ctim,PyTuple_GET_ITEM(v,directory?6:8));
}
static int private_meta(struct stat *s,unsigned long long uid,unsigned long long gid,int directory) {
    return (directory?S_ISDIR(s->st_mode):S_ISREG(s->st_mode)) &&
        (unsigned long long)s->st_uid==uid && (unsigned long long)s->st_gid==gid &&
        (s->st_mode&07777)==(directory?0700:0600) &&
        (directory || (s->st_nlink==1 && s->st_size<=131072));
}
static PyObject *meta8(struct stat *s) {
    PyObject *v=PyTuple_New(8),*item;if(!v)return NULL;
    if(put_unsigned(v,0,(unsigned long long)s->st_dev)<0 || put_unsigned(v,1,(unsigned long long)s->st_ino)<0)goto error;
    item=PyLong_FromLongLong((long long)s->st_size);if(!item)goto error;PyTuple_SET_ITEM(v,2,item);
    item=nanoseconds(s->st_mtim.tv_sec,s->st_mtim.tv_nsec);if(!item)goto error;PyTuple_SET_ITEM(v,3,item);
    item=nanoseconds(s->st_ctim.tv_sec,s->st_ctim.tv_nsec);if(!item)goto error;PyTuple_SET_ITEM(v,4,item);
    if(put_unsigned(v,5,(unsigned long long)s->st_uid)<0 || put_unsigned(v,6,(unsigned long long)s->st_mode)<0 ||
       put_unsigned(v,7,(unsigned long long)s->st_nlink)<0)goto error;
    return v;
error:Py_DECREF(v);return NULL;
}
static int add_meta(PyObject *result,PyObject *key,struct stat *s,int full) {
    PyObject *v=full?meta8(s):Py_BuildValue("(KKkk)",(unsigned long long)s->st_dev,(unsigned long long)s->st_ino,
        (unsigned long)s->st_uid,(unsigned long)s->st_mode);int r;
    if(!v)return -1;
    r=PyDict_SetItem(result,key,v);Py_DECREF(v);return r;
}

/* Complete reads keep CPython's original buffering, maximum+1 read and GIL /
 * EINTR behavior. The I/O wrapper borrows the newly opened descriptor;
 * this backend alone closes it once, after the original after-read fstat.
 * https://docs.python.org/3.12/library/functions.html#open
 * https://github.com/python/cpython/blob/v3.12.3/Modules/_io/fileio.c
 * No data or metadata survives a call except its fresh return value. */
static int read_open(PyObject *name,int flags) {
    PyObject *encoded;int fd,saved;
    if(PyErr_CheckSignals()<0)return -1;
    encoded=PyUnicode_EncodeFSDefault(name);if(!encoded)return -1;
    if(memchr(PyBytes_AS_STRING(encoded),0,(size_t)PyBytes_GET_SIZE(encoded))) {
        Py_DECREF(encoded);PyErr_SetString(PyExc_ValueError,"embedded null byte");return -1;
    }
    if(PySys_Audit("open","OOi",name,Py_None,flags)<0){Py_DECREF(encoded);return -1;}
    for(;;) {
        Py_BEGIN_ALLOW_THREADS
        fd=open(PyBytes_AS_STRING(encoded),flags);saved=errno;
        Py_END_ALLOW_THREADS
        if(fd>=0||saved!=EINTR)break;
        if(PyErr_CheckSignals()<0){Py_DECREF(encoded);return -1;}
    }
    Py_DECREF(encoded);
    if(fd<0){errno=saved;PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError,name);}
    return fd;
}

static int close_read(PyObject *reader,int fd) {
    PyObject *pending=PyErr_GetRaisedException(),*cleanup=NULL,*closed;
    int result,saved;
    if(reader) {
        closed=PyObject_CallMethod(reader,"close",NULL);
        if(!closed)cleanup=PyErr_GetRaisedException();
        Py_XDECREF(closed);
    }
    if(fd>=0) {
        /* Never retry close after EINTR: the descriptor may already be gone. */
        Py_BEGIN_ALLOW_THREADS
        result=close(fd);saved=errno;
        Py_END_ALLOW_THREADS
        if(result<0&&!cleanup){errno=saved;PyErr_SetFromErrno(PyExc_OSError);cleanup=PyErr_GetRaisedException();}
    }
    if(pending){Py_XDECREF(cleanup);PyErr_SetRaisedException(pending);return -1;}
    if(cleanup){PyErr_SetRaisedException(cleanup);return -1;}
    return 0;
}

static int reader_fd(PyObject *reader,int expected) {
    PyObject *value=PyObject_CallMethod(reader,"fileno",NULL);long actual;
    if(!value)return -1;
    actual=PyLong_AsLong(value);Py_DECREF(value);
    if(actual==-1&&PyErr_Occurred())return -1;
    if(actual!=expected){PyErr_SetString(PyExc_ValueError,"Owned reader descriptor changed");return -1;}
    return expected;
}

static PyObject *read_file(PyObject *unused,PyObject *args) {
    PyObject *kind_o,*name,*parents,*uid_o,*maximum_o,*executable_o,*opener,*reader_type;
    PyObject *reader=NULL,*call_args=NULL,*keywords=NULL,*entered=NULL,*raw=NULL;
    PyObject *before=NULL,*after=NULL,*result=NULL;
    unsigned long long uid;long long maximum;long kind;Py_ssize_t i;int fd=-1,flags,r;
    struct stat info;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOOOOOO",&kind_o,&name,&parents,&uid_o,&maximum_o,&executable_o,&opener,&reader_type))return NULL;
    if(!PyLong_CheckExact(kind_o)||!PyUnicode_CheckExact(name)||PyUnicode_GET_LENGTH(name)>8192 ||
       !PyTuple_CheckExact(parents)||PyTuple_GET_SIZE(parents)>64||!PyBool_Check(executable_o)||
       !PyCFunction_Check(opener)||!PyType_Check(reader_type))goto unsupported;
    kind=PyLong_AsLong(kind_o);if(PyErr_Occurred())return NULL;
    if(kind<0||kind>3)goto unsupported;
    r=u64(uid_o,&uid);if(r<=0)goto unsupported;
    r=i64(maximum_o,&maximum);if(r<=0)goto unsupported;
    if(maximum<0||maximum>16777216||((kind==0||kind==1)&&maximum==0))goto unsupported;
    if((kind!=1&&uid!=0)||(kind!=0&&executable_o!=Py_False)||(kind>=2&&PyTuple_GET_SIZE(parents)!=0))goto unsupported;
    for(i=0;i<PyTuple_GET_SIZE(parents);i++) {
        PyObject *parent=PyTuple_GET_ITEM(parents,i);
        if(!PyUnicode_CheckExact(parent)||PyUnicode_GET_LENGTH(parent)>8192)goto unsupported;
    }
    if(++read_calls>10000000){PyErr_SetString(PyExc_RuntimeError,"Read probe counter bound");return NULL;}
    for(i=0;i<PyTuple_GET_SIZE(parents);i++) {
        if(fresh_lstat(PyTuple_GET_ITEM(parents,i),&info)<0)goto done;
        if(!S_ISDIR(info.st_mode)||(kind==0&&(info.st_uid!=0||(info.st_mode&0022))))goto refused;
    }
    if(kind==1) {
        if(fresh_lstat(name,&info)<0)goto done;
        if(!S_ISREG(info.st_mode))goto refused;
    }
    flags=O_RDONLY|O_NOFOLLOW|O_CLOEXEC;
    if(kind==1||kind==3)flags|=O_NONBLOCK;
    fd=read_open(name,flags);if(fd<0)goto done;
    call_args=Py_BuildValue("(is)",fd,"rb");keywords=Py_BuildValue("{sO}","closefd",Py_False);
    if(!call_args||!keywords)goto done;
    reader=PyObject_Call(opener,call_args,keywords);if(!reader)goto done;
    if(!Py_IS_TYPE(reader,(PyTypeObject *)reader_type)) {
        PyErr_SetString(PyExc_ValueError,"Unsupported owned buffered reader");goto done;
    }
    entered=PyObject_CallMethod(reader,"__enter__",NULL);if(!entered)goto done;
    if(entered!=reader){PyErr_SetString(PyExc_ValueError,"Owned reader entry changed");goto done;}
    if(kind<2) {
        if(reader_fd(reader,fd)<0||fresh_fd(fd,&info)<0)goto done;
        if(!S_ISREG(info.st_mode)||(unsigned long long)info.st_uid!=uid||info.st_nlink!=1||
            info.st_size<=0||info.st_size>maximum ||
            (kind==0?((info.st_mode&0022)!=0 || (executable_o==Py_True&&!(info.st_mode&0111))):
                (info.st_mode&07777)!=0600))goto refused;
        before=meta8(&info);if(!before)goto done;
    } else {before=Py_NewRef(Py_None);after=Py_NewRef(Py_None);}
    raw=PyObject_CallMethod(reader,"read","n",(Py_ssize_t)(maximum+1));if(!raw)goto done;
    if(kind<2) {
        if(reader_fd(reader,fd)<0||fresh_fd(fd,&info)<0)goto done;
        after=meta8(&info);if(!after)goto done;
    }
    /* The original length, metadata equality, hash and ASCII checks occur
     * after the same close boundary in the Python family wrapper. raw=None
     * from a nonblocking reader is preserved for the original len error. */
    result=PyTuple_Pack(3,raw,before,after);goto done;
refused:result=Py_NewRef(Py_None);
done:
    if(close_read(reader,fd)<0)Py_CLEAR(result);
    Py_XDECREF(reader);Py_XDECREF(call_args);Py_XDECREF(keywords);Py_XDECREF(entered);
    Py_XDECREF(raw);Py_XDECREF(before);Py_XDECREF(after);return result;
unsupported:if(PyErr_Occurred())return NULL;Py_RETURN_NOTIMPLEMENTED;
}

static PyObject *read_counts(PyObject *unused,PyObject *args) {
    (void)unused;(void)args;
    return Py_BuildValue("{sK,sK}","read",read_calls,"prepare",prepare_calls);
}

/* Convert only finite lexical tables from an exact original instance. Never
 * call a data descriptor, custom attribute reader, or filesystem hook here.
 * Unsupported schemas return before the persistent/custody observation API. */
static PyObject *plain_fields(PyObject *subject,PyObject *expected,const char **fields) {
    PyObject *mro,*dict;Py_ssize_t i,j;
    if(!PyType_Check(expected)||!Py_IS_TYPE(subject,(PyTypeObject *)expected)||
       Py_TYPE(subject)->tp_getattro!=PyObject_GenericGetAttr)return Py_NewRef(Py_NotImplemented);
    mro=Py_TYPE(subject)->tp_mro;
    if(!mro||!PyTuple_CheckExact(mro))return Py_NewRef(Py_NotImplemented);
    Py_INCREF(mro);
    for(i=0;fields[i];i++)for(j=0;j<PyTuple_GET_SIZE(mro);j++) {
        /* CPython 3.12 stores static builtin namespaces per interpreter;
         * object->tp_dict can be NULL even for a ready builtin ancestor.
         * PyType_GetDict returns a new reference to the actual namespace.
         * https://docs.python.org/3.12/c-api/type.html#c.PyType_GetDict */
        dict=PyType_GetDict((PyTypeObject *)PyTuple_GET_ITEM(mro,j));
        if(!dict){Py_DECREF(mro);if(PyErr_Occurred())return NULL;return Py_NewRef(Py_NotImplemented);}
        int present=PyDict_GetItemString(dict,fields[i])!=NULL;
        Py_DECREF(dict);
        if(present){Py_DECREF(mro);return Py_NewRef(Py_NotImplemented);}
    }
    Py_DECREF(mro);
    dict=PyObject_GenericGetDict(subject,NULL);
    if(!dict) {
        if(PyErr_ExceptionMatches(PyExc_AttributeError)){PyErr_Clear();return Py_NewRef(Py_NotImplemented);}
        return NULL;
    }
    if(!PyDict_CheckExact(dict)){Py_DECREF(dict);return Py_NewRef(Py_NotImplemented);}
    for(i=0;fields[i];i++)if(!PyDict_GetItemString(dict,fields[i])) {
        Py_DECREF(dict);return Py_NewRef(Py_NotImplemented);
    }
    return dict;
}
static PyObject *lexical_path(PyObject *path,PyObject *path_type) {
    PyObject *name;
    if(!Py_IS_TYPE(path,(PyTypeObject *)path_type))return Py_NewRef(Py_NotImplemented);
    name=PyObject_Str(path);if(!name)return NULL;
    if(!PyUnicode_CheckExact(name)||PyUnicode_GET_LENGTH(name)>8192) {
        Py_DECREF(name);return Py_NewRef(Py_NotImplemented);
    }
    return name;
}
static PyObject *path_rows(PyObject *source,PyObject *path_type,const char *spec,Py_ssize_t limit,int names) {
    PyObject *result,*v,*name,*copy,*set,*tuple;Py_ssize_t i,j,n=(Py_ssize_t)strlen(spec);int r;
    if(!PyTuple_CheckExact(source)||PyTuple_GET_SIZE(source)>limit)return Py_NewRef(Py_NotImplemented);
    result=PyTuple_New(PyTuple_GET_SIZE(source));if(!result)return NULL;
    for(i=0;i<PyTuple_GET_SIZE(source);i++) {
        v=PyTuple_GET_ITEM(source,i);
        if(!PyTuple_CheckExact(v)||PyTuple_GET_SIZE(v)!=n)goto unsupported;
        name=lexical_path(PyTuple_GET_ITEM(v,0),path_type);
        if(!name)goto error;
        if(name==Py_NotImplemented){Py_DECREF(name);goto unsupported;}
        copy=PyTuple_New(n);if(!copy){Py_DECREF(name);goto error;}
        PyTuple_SET_ITEM(copy,0,name);
        for(j=1;j<n;j++)PyTuple_SET_ITEM(copy,j,Py_NewRef(PyTuple_GET_ITEM(v,j)));
        if(names) {
            set=PyTuple_GET_ITEM(v,1);
            if(!PyFrozenSet_CheckExact(set)||PySet_GET_SIZE(set)>1024){Py_DECREF(copy);goto unsupported;}
            tuple=PySequence_Tuple(set);if(!tuple){Py_DECREF(copy);goto error;}
            Py_DECREF(PyTuple_GET_ITEM(copy,1));PyTuple_SET_ITEM(copy,1,tuple);
            for(j=0;j<PyTuple_GET_SIZE(tuple);j++)if(!PyUnicode_CheckExact(PyTuple_GET_ITEM(tuple,j))) {
                Py_DECREF(copy);goto unsupported;
            }
        }
        r=row(copy,spec);if(r<=0){Py_DECREF(copy);if(r<0)goto error;goto unsupported;}
        PyTuple_SET_ITEM(result,i,copy);
    }
    return result;
unsupported:Py_DECREF(result);return Py_NewRef(Py_NotImplemented);
error:Py_DECREF(result);return NULL;
}
static PyObject *prepare_plan(PyObject *subject,PyObject *owner,PyObject *path_type) {
    const char *fields[]={"uid","entries","directories","machine","files","parents",NULL};
    PyObject *dict=plain_fields(subject,owner,fields),*entries=NULL,*dirs=NULL,*machine=NULL,*files=NULL,*parents=NULL,*result=NULL;
    unsigned long long uid;int r;
    if(!dict||dict==Py_NotImplemented)return dict;
    r=u64(PyDict_GetItemString(dict,"uid"),&uid);if(r<=0)goto unsupported;
    entries=path_rows(PyDict_GetItemString(dict,"entries"),path_type,"st",16,1);
    if(!entries)goto done;
    if(entries==Py_NotImplemented)goto unsupported;
    dirs=path_rows(PyDict_GetItemString(dict,"directories"),path_type,"ssuuu",64,0);
    if(!dirs)goto done;
    if(dirs==Py_NotImplemented)goto unsupported;
    machine=lexical_path(PyDict_GetItemString(dict,"machine"),path_type);
    if(!machine)goto done;
    if(machine==Py_NotImplemented)goto unsupported;
    files=path_rows(PyDict_GetItemString(dict,"files"),path_type,"ssubnuu",64,0);
    if(!files)goto done;
    if(files==Py_NotImplemented)goto unsupported;
    parents=path_rows(PyDict_GetItemString(dict,"parents"),path_type,"ssbb",256,0);
    if(!parents)goto done;
    if(parents==Py_NotImplemented)goto unsupported;
    result=PyTuple_Pack(6,PyDict_GetItemString(dict,"uid"),entries,dirs,machine,files,parents);goto done;
unsupported:if(!PyErr_Occurred())result=Py_NewRef(Py_NotImplemented);
done:Py_DECREF(dict);Py_XDECREF(entries);Py_XDECREF(dirs);Py_XDECREF(machine);Py_XDECREF(files);Py_XDECREF(parents);return result;
}
static int descriptor(PyObject *value) {
    unsigned long long fd;int r=u64(value,&fd);return r<=0?r:fd<=INT_MAX;
}
static PyObject *parent_descriptor(PyObject *directories,PyObject *path) {
    PyObject *parent=PyObject_GetAttrString(path,"parent"),*item;
    if(!parent)return NULL;
    item=PyDict_GetItemWithError(directories,parent);Py_DECREF(parent);
    if(!item){if(PyErr_Occurred())return NULL;return Py_NewRef(Py_NotImplemented);}
    if(!PyTuple_CheckExact(item)||PyTuple_GET_SIZE(item)!=2)return Py_NewRef(Py_NotImplemented);
    return Py_NewRef(PyTuple_GET_ITEM(item,0));
}
static PyObject *prepare_custody(PyObject *subject,PyObject *owner,PyObject *path_type) {
    const char *fields[]={"uid","gid","root","directory","lock_path","directories","known","retained","entries","directory_metadata","lock",NULL};
    PyObject *dict=plain_fields(subject,owner,fields),*directories,*known,*retained,*entries,*metadata;
    PyObject *rows_o=NULL,*leaves=NULL,*lock=NULL,*path,*item,*original,*extra,*names;
    PyObject *name=NULL,*parent=NULL,*temp=NULL,*result=NULL,*v;Py_ssize_t pos=0,i=0;unsigned long long uid,gid;int r,equal;
    if(!dict||dict==Py_NotImplemented)return dict;
    r=u64(PyDict_GetItemString(dict,"uid"),&uid);if(r<=0)goto unsupported;
    r=u64(PyDict_GetItemString(dict,"gid"),&gid);if(r<=0)goto unsupported;
    for(i=2;i<5;i++) {
        temp=lexical_path(PyDict_GetItemString(dict,fields[i]),path_type);
        if(!temp)goto done;
        if(temp==Py_NotImplemented)goto unsupported;
        Py_CLEAR(temp);
    }
    directories=PyDict_GetItemString(dict,"directories");known=PyDict_GetItemString(dict,"known");
    retained=PyDict_GetItemString(dict,"retained");entries=PyDict_GetItemString(dict,"entries");metadata=PyDict_GetItemString(dict,"directory_metadata");
    if(!PyDict_CheckExact(directories)||PyDict_GET_SIZE(directories)>256 || !PyDict_CheckExact(known)||PyDict_GET_SIZE(known)>1024 ||
       !PyDict_CheckExact(retained)||!PyDict_CheckExact(metadata)||(entries!=Py_None&&!PyDict_CheckExact(entries)))goto unsupported;
    rows_o=PyTuple_New(PyDict_GET_SIZE(directories));leaves=PyTuple_New(PyDict_GET_SIZE(known));if(!rows_o||!leaves)goto done;
    i=0;
    while(PyDict_Next(directories,&pos,&path,&item)) {
        if(!Py_IS_TYPE(path,(PyTypeObject *)path_type)||!PyTuple_CheckExact(item)||PyTuple_GET_SIZE(item)!=2)goto unsupported;
        r=descriptor(PyTuple_GET_ITEM(item,0));if(r<=0)goto unsupported;
        original=PyTuple_GET_ITEM(item,1);r=row(original,"uuuuunn");if(r<=0)goto unsupported;
        equal=PyObject_RichCompareBool(path,PyDict_GetItemString(dict,"directory"),Py_EQ);if(equal<0)goto done;
        if(equal){parent=Py_NewRef(Py_None);name=lexical_path(path,path_type);}
        else {
            parent=parent_descriptor(directories,path);if(!parent)goto done;
            if(parent==Py_NotImplemented)goto unsupported;
            r=descriptor(parent);if(r<=0)goto unsupported;
            name=PyObject_GetAttrString(path,"name");
        }
        if(!name)goto done;
        if(name==Py_NotImplemented)goto unsupported;
        extra=entries==Py_None?Py_None:PyDict_GetItemWithError(metadata,path);
        names=entries==Py_None?Py_None:PyDict_GetItemWithError(entries,path);
        if(!extra||!names){if(PyErr_Occurred())goto done;goto unsupported;}
        if(entries!=Py_None){r=row(extra,"uuuuuunnn");if(r<=0)goto unsupported;if(!strings(names,0))goto unsupported;}
        v=PyTuple_Pack(6,name,parent,PyTuple_GET_ITEM(item,0),original,extra,names);if(!v)goto done;
        r=row(v,"szutOL");if(r<=0){Py_DECREF(v);goto unsupported;}
        PyTuple_SET_ITEM(rows_o,i++,v);Py_CLEAR(parent);Py_CLEAR(name);
    }
    pos=0;i=0;
    while(PyDict_Next(known,&pos,&path,&original)) {
        if(!Py_IS_TYPE(path,(PyTypeObject *)path_type))goto unsupported;
        r=row(original,"uuuuuunnn");if(r<=0)goto unsupported;
        parent=parent_descriptor(directories,path);if(!parent)goto done;
        if(parent==Py_NotImplemented)goto unsupported;
        r=descriptor(parent);if(r<=0)goto unsupported;
        item=PyDict_GetItemWithError(retained,path);if(!item&&PyErr_Occurred())goto done;
        if(item){r=descriptor(item);if(r<=0)goto unsupported;}else item=Py_None;
        name=PyObject_GetAttrString(path,"name");if(!name)goto done;
        v=PyTuple_Pack(4,name,parent,original,item);if(!v)goto done;
        r=row(v,"sutz");if(r<=0){Py_DECREF(v);goto unsupported;}
        PyTuple_SET_ITEM(leaves,i++,v);Py_CLEAR(parent);Py_CLEAR(name);
    }
    item=PyDict_GetItemString(dict,"lock");
    if(item==Py_None)lock=Py_NewRef(Py_None);
    else {
        r=descriptor(item);if(r<=0)goto unsupported;
        original=PyDict_GetItemWithError(known,PyDict_GetItemString(dict,"lock_path"));
        if(!original){if(PyErr_Occurred())goto done;goto unsupported;}
        r=row(original,"uuuuuunnn");if(r<=0)goto unsupported;
        lock=PyTuple_Pack(2,item,original);if(!lock)goto done;
    }
    result=PyTuple_Pack(5,PyDict_GetItemString(dict,"uid"),PyDict_GetItemString(dict,"gid"),rows_o,leaves,lock);goto done;
unsupported:if(!PyErr_Occurred())result=Py_NewRef(Py_NotImplemented);
done:Py_DECREF(dict);Py_XDECREF(rows_o);Py_XDECREF(leaves);Py_XDECREF(lock);Py_XDECREF(name);Py_XDECREF(parent);Py_XDECREF(temp);return result;
}
static PyObject *prepare_tables(PyObject *unused,PyObject *args) {
    PyObject *kind_o,*subject,*owner,*path_type,*result;long kind;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOO",&kind_o,&subject,&owner,&path_type))return NULL;
    if(!PyLong_CheckExact(kind_o)||!PyType_Check(path_type))Py_RETURN_NOTIMPLEMENTED;
    kind=PyLong_AsLong(kind_o);if(PyErr_Occurred())return NULL;
    if(kind==0)result=prepare_plan(subject,owner,path_type);
    else if(kind==1)result=prepare_custody(subject,owner,path_type);
    else Py_RETURN_NOTIMPLEMENTED;
    if(result&&result!=Py_NotImplemented&&++prepare_calls>10000000) {
        Py_DECREF(result);PyErr_SetString(PyExc_RuntimeError,"Preparation probe counter bound");return NULL;
    }
    return result;
}

static PyObject *persistent(PyObject *unused,PyObject *args) {
    PyObject *uid_o,*entries,*dirs,*machine,*files,*parents,*listdir,*result=NULL;
    unsigned long long uid;Py_ssize_t i,j;int r;struct stat info;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOOOOO",&uid_o,&entries,&dirs,&machine,&files,&parents,&listdir))return NULL;
    r=u64(uid_o,&uid);if(r<=0)goto unsupported;
    r=rows(entries,"st",16);if(r<=0)goto unsupported;
    r=rows(dirs,"ssuuu",64);if(r<=0)goto unsupported;
    r=rows(files,"ssubnuu",64);if(r<=0)goto unsupported;
    r=rows(parents,"ssbb",256);if(r<=0)goto unsupported;
    if(!PyUnicode_CheckExact(machine)||!PyCallable_Check(listdir))goto unsupported;
    for(i=0;i<PyTuple_GET_SIZE(entries);i++) {
        PyObject *names=PyTuple_GET_ITEM(PyTuple_GET_ITEM(entries,i),1);
        if(PyTuple_GET_SIZE(names)>1024)goto unsupported;
        for(j=0;j<PyTuple_GET_SIZE(names);j++)if(!PyUnicode_CheckExact(PyTuple_GET_ITEM(names,j)))goto unsupported;
    }
    if(++plan_calls>10000000){PyErr_SetString(PyExc_RuntimeError,"Metadata probe counter bound");return NULL;}
    result=PyDict_New();if(!result)return NULL;
    for(i=0;i<PyTuple_GET_SIZE(entries);i++) {
        PyObject *v=PyTuple_GET_ITEM(entries,i),*names=PyObject_CallOneArg(listdir,PyTuple_GET_ITEM(v,0));
        PyObject *actual=NULL,*expected=NULL;
        if(!names)goto error;
        actual=PySet_New(names);Py_DECREF(names);if(!actual)goto error;
        expected=PySet_New(PyTuple_GET_ITEM(v,1));if(!expected){Py_DECREF(actual);goto error;}
        r=PyObject_RichCompareBool(actual,expected,Py_EQ);Py_DECREF(actual);Py_DECREF(expected);
        if(r<0)goto error;
        if(!r)goto refused;
    }
    for(i=0;i<PyTuple_GET_SIZE(dirs);i++) {
        PyObject *v=PyTuple_GET_ITEM(dirs,i);
        if(fresh_lstat(PyTuple_GET_ITEM(v,0),&info)<0)goto error;
        if(!S_ISDIR(info.st_mode)||(unsigned long long)info.st_uid!=uid||(info.st_mode&07777)!=0700 ||
            (unsigned long long)info.st_dev!=PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,2)) ||
            (unsigned long long)info.st_ino!=PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,3)) ||
            (unsigned long long)info.st_uid!=PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,4)))goto refused;
        if(add_meta(result,PyTuple_GET_ITEM(v,1),&info,0)<0)goto error;
    }
    if(fresh_lstat(machine,&info)<0)goto error;
    if(!S_ISREG(info.st_mode)||info.st_uid!=0||info.st_nlink!=1||(info.st_mode&0022))goto refused;
    if(add_meta(result,machine,&info,1)<0)goto error;
    for(i=0;i<PyTuple_GET_SIZE(files);i++) {
        PyObject *v=PyTuple_GET_ITEM(files,i);unsigned long long owner=PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,2));
        if(fresh_lstat(PyTuple_GET_ITEM(v,0),&info)<0)goto error;
        if(!S_ISREG(info.st_mode)||(unsigned long long)info.st_uid!=owner||info.st_nlink!=1 ||
            (long long)info.st_size!=PyLong_AsLongLong(PyTuple_GET_ITEM(v,4)) ||
            (unsigned long long)info.st_dev!=PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,5)) ||
            (unsigned long long)info.st_ino!=PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(v,6)) ||
            (owner==0?(info.st_mode&0022)!=0:(info.st_mode&07777)!=0600) ||
            (PyTuple_GET_ITEM(v,3)==Py_True && !(info.st_mode&0111)))goto refused;
        if(add_meta(result,PyTuple_GET_ITEM(v,1),&info,1)<0)goto error;
    }
    for(i=0;i<PyTuple_GET_SIZE(parents);i++) {
        PyObject *v=PyTuple_GET_ITEM(parents,i);
        if(fresh_lstat(PyTuple_GET_ITEM(v,0),&info)<0)goto error;
        if(!S_ISDIR(info.st_mode))goto refused;
        if(PyTuple_GET_ITEM(v,2)==Py_True) {
            if(PyTuple_GET_ITEM(v,3)==Py_True) {
                if((unsigned long long)info.st_uid!=uid||(info.st_mode&07777)!=0700)goto refused;
            } else if(info.st_uid!=0||(info.st_mode&0022))goto refused;
            if(add_meta(result,PyTuple_GET_ITEM(v,1),&info,0)<0)goto error;
        }
    }
    return result;
refused:Py_DECREF(result);Py_RETURN_NONE;
error:Py_XDECREF(result);return NULL;
unsupported:if(PyErr_Occurred())return NULL;Py_RETURN_NOTIMPLEMENTED;
}
static PyObject *custody(PyObject *unused,PyObject *args) {
    PyObject *uid_o,*gid_o,*dirs,*known,*lock,*names;unsigned long long uid,gid,fd;
    Py_ssize_t i;int r;struct stat named,held;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOOOO",&uid_o,&gid_o,&dirs,&known,&lock,&names))return NULL;
    r=u64(uid_o,&uid);if(r<=0)goto unsupported;r=u64(gid_o,&gid);if(r<=0)goto unsupported;
    r=rows(dirs,"szutOL",256);if(r<=0)goto unsupported;r=rows(known,"sutz",1024);if(r<=0)goto unsupported;
    if(!PyCallable_Check(names))goto unsupported;
    for(i=0;i<PyTuple_GET_SIZE(dirs);i++) {
        PyObject *v=PyTuple_GET_ITEM(dirs,i);r=row(PyTuple_GET_ITEM(v,3),"uuuuunn");if(r<=0)goto unsupported;
        r=u64(PyTuple_GET_ITEM(v,2),&fd);if(r<=0||fd>INT_MAX)goto unsupported;
        if(PyTuple_GET_ITEM(v,4)!=Py_None){r=row(PyTuple_GET_ITEM(v,4),"uuuuuunnn");if(r<=0)goto unsupported;}
        if((PyTuple_GET_ITEM(v,4)==Py_None)!=(PyTuple_GET_ITEM(v,5)==Py_None))goto unsupported;
    }
    for(i=0;i<PyTuple_GET_SIZE(known);i++) {
        PyObject *v=PyTuple_GET_ITEM(known,i);r=row(PyTuple_GET_ITEM(v,2),"uuuuuunnn");if(r<=0)goto unsupported;
        r=u64(PyTuple_GET_ITEM(v,1),&fd);if(r<=0||fd>INT_MAX)goto unsupported;
    }
    if(lock!=Py_None){r=row(lock,"ut");if(r<=0)goto unsupported;r=row(PyTuple_GET_ITEM(lock,1),"uuuuuunnn");if(r<=0)goto unsupported;
        r=u64(PyTuple_GET_ITEM(lock,0),&fd);if(r<=0||fd>INT_MAX)goto unsupported;}
    if(++custody_calls>10000000){PyErr_SetString(PyExc_RuntimeError,"Metadata probe counter bound");return NULL;}
    for(i=0;i<PyTuple_GET_SIZE(dirs);i++) {
        PyObject *v=PyTuple_GET_ITEM(dirs,i),*parent=PyTuple_GET_ITEM(v,1),*expected=PyTuple_GET_ITEM(v,3);
        int held_fd=(int)PyLong_AsLong(PyTuple_GET_ITEM(v,2));
        if(parent==Py_None){if(fresh_lstat(PyTuple_GET_ITEM(v,0),&named)<0)return NULL;}
        else if(fresh_at(PyTuple_GET_ITEM(v,0),(int)PyLong_AsLong(parent),&named)<0)return NULL;
        if(fresh_fd(held_fd,&held)<0)return NULL;
        if(!private_meta(&held,uid,gid,1))Py_RETURN_FALSE;
        r=equal_meta(&held,expected,1);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
        if(!private_meta(&named,uid,gid,1))Py_RETURN_FALSE;
        r=equal_meta(&named,expected,1);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
        if(PyTuple_GET_ITEM(v,4)!=Py_None) {
            PyObject *observed;
            /* This is the original second fstat; do not merge it with the first. */
            if(fresh_fd(held_fd,&held)<0)return NULL;
            r=equal_meta(&held,PyTuple_GET_ITEM(v,4),0);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
            r=equal_meta(&named,PyTuple_GET_ITEM(v,4),0);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
            observed=PyObject_CallOneArg(names,PyTuple_GET_ITEM(v,2));if(!observed)return NULL;
            r=PyObject_RichCompareBool(observed,PyTuple_GET_ITEM(v,5),Py_EQ);Py_DECREF(observed);
            if(r<0)return NULL;
            if(!r)Py_RETURN_FALSE;
        }
    }
    for(i=0;i<PyTuple_GET_SIZE(known);i++) {
        PyObject *v=PyTuple_GET_ITEM(known,i),*expected=PyTuple_GET_ITEM(v,2),*retained=PyTuple_GET_ITEM(v,3);
        if(fresh_at(PyTuple_GET_ITEM(v,0),(int)PyLong_AsLong(PyTuple_GET_ITEM(v,1)),&named)<0)return NULL;
        if(!private_meta(&named,uid,gid,0))Py_RETURN_FALSE;
        r=equal_meta(&named,expected,0);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
        if(retained!=Py_None) {
            if(fresh_fd((int)PyLong_AsLong(retained),&held)<0)return NULL;
            if(!private_meta(&held,uid,gid,0))Py_RETURN_FALSE;
            r=equal_meta(&held,expected,0);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
        }
    }
    if(lock!=Py_None) {
        if(fresh_fd((int)PyLong_AsLong(PyTuple_GET_ITEM(lock,0)),&held)<0)return NULL;
        if(!private_meta(&held,uid,gid,0))Py_RETURN_FALSE;
        r=equal_meta(&held,PyTuple_GET_ITEM(lock,1),0);if(r<0)return NULL;if(!r)Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
unsupported:if(PyErr_Occurred())return NULL;Py_RETURN_NOTIMPLEMENTED;
}
static PyObject *same_bindings(PyObject *unused,PyObject *args) {
    PyObject *bindings,*pid_o,*tid_o;unsigned long long pid,tid;Py_ssize_t i;int r;(void)unused;
    if(!PyArg_ParseTuple(args,"OOO",&bindings,&pid_o,&tid_o))return NULL;
    r=u64(pid_o,&pid);if(r<=0)goto unsupported;r=u64(tid_o,&tid);if(r<=0)goto unsupported;
    r=rows(bindings,"OsO",256);if(r<=0)goto unsupported;
    if(pid!=(unsigned long long)getpid()||tid!=(unsigned long long)PyThread_get_thread_ident()||
        getuid()!=0||geteuid()!=0||getgid()!=0||getegid()!=0)Py_RETURN_FALSE;
    for(i=0;i<PyTuple_GET_SIZE(bindings);i++) {
        PyObject *v=PyTuple_GET_ITEM(bindings,i),*owner=PyTuple_GET_ITEM(v,0),*current;
        if(PyFunction_Check(owner)) {
            if(PyUnicode_CompareWithASCIIString(PyTuple_GET_ITEM(v,1),"__code__")!=0) {
                PyErr_SetString(PyExc_TypeError,"Unsupported metadata function binding");return NULL;
            }
            current=Py_NewRef(PyFunction_GetCode(owner));
        } else if(PyType_Check(owner))current=PyObject_GetAttr(owner,PyTuple_GET_ITEM(v,1));
        else current=PyObject_GetItem(owner,PyTuple_GET_ITEM(v,1));
        if(!current){if(PyErr_ExceptionMatches(PyExc_KeyError)||PyErr_ExceptionMatches(PyExc_AttributeError)){PyErr_Clear();Py_RETURN_FALSE;}return NULL;}
        if(PyType_Check(owner)&&PyMethod_Check(current)&&PyMethod_Check(PyTuple_GET_ITEM(v,2))) {
            PyObject *expected=PyTuple_GET_ITEM(v,2);
            r=PyMethod_GET_FUNCTION(current)==PyMethod_GET_FUNCTION(expected)&&PyMethod_GET_SELF(current)==PyMethod_GET_SELF(expected);
        } else r=current==PyTuple_GET_ITEM(v,2);
        Py_DECREF(current);if(!r)Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
unsupported:if(PyErr_Occurred())return NULL;PyErr_SetString(PyExc_TypeError,"Invalid metadata hook bindings");return NULL;
}
static PyObject *counts(PyObject *unused,PyObject *args) {
    (void)unused;(void)args;
    return Py_BuildValue("{sK,sK,sK}","fingerprint",fingerprint_calls,"persistent",plan_calls,"custody",custody_calls);
}
/* Pure lexical SDK candidate. The cache owns immutable strings/tuples only.
 * Admission is performed afresh; a prepared schema is not an admission result.
 * PyType_GetDict is required for static per-interpreter type namespaces. */
#define LEX_CAPSULE "_native_metadata_probe.path_plan.v1"
#define LEX_LIMIT 10000000ULL
typedef struct LexPlan LexPlan;
struct LexPlan {
    PyObject *tables,*cls,*mro,*cache,*names[5],*empty,*slash,*double_slash,*dot,*import_globals,*import_name;
    PyObject *import_module,*import_spec,*import_spec_type,*initializing;
    unsigned long long pid,thread,calls[4],hits,misses;
    Py_ssize_t capacity;
    int broken;
    int (*guard)(LexPlan *,int);
    void *code_context;
};

static void lex_free(LexPlan *p) {
    int i;
    if(!p)return;
    Py_XDECREF(p->tables);Py_XDECREF(p->cls);Py_XDECREF(p->mro);Py_XDECREF(p->cache);
    for(i=0;i<5;i++)Py_XDECREF(p->names[i]);
    Py_XDECREF(p->empty);Py_XDECREF(p->slash);Py_XDECREF(p->double_slash);Py_XDECREF(p->dot);
    Py_XDECREF(p->import_globals);Py_XDECREF(p->import_name);
    Py_XDECREF(p->import_module);Py_XDECREF(p->import_spec);Py_XDECREF(p->import_spec_type);Py_XDECREF(p->initializing);
    PyMem_Free(p);
}
static void lex_destroy(PyObject *capsule) {
    PyObject *pending=PyErr_GetRaisedException();
    LexPlan *p=PyCapsule_GetPointer(capsule,LEX_CAPSULE);
    if(p)lex_free(p);else PyErr_Clear();
    PyErr_SetRaisedException(pending);
}
static int lex_owner(LexPlan *p) {
    uid_t real_uid,effective_uid,saved_uid;
    gid_t real_gid,effective_gid,saved_gid;
    if(p->pid!=(unsigned long long)getpid()||
        p->thread!=(unsigned long long)PyThread_get_thread_ident())return 0;
    /* Fresh values, never an identity lease. Each query returns the existing
     * real/effective fields together; saved IDs are not used for admission.
     * https://man7.org/linux/man-pages/man2/getresuid.2.html */
    if(getresuid(&real_uid,&effective_uid,&saved_uid)<0||
        getresgid(&real_gid,&effective_gid,&saved_gid)<0)return 0;
    return real_uid==0&&effective_uid==0&&real_gid==0&&effective_gid==0;
}
static PyObject *lex_type_binding(PyObject *owner,PyObject *key) {
    PyObject *mro=((PyTypeObject *)owner)->tp_mro,*result=NULL;Py_ssize_t i;
    if(!mro||!PyTuple_CheckExact(mro)||PyTuple_GET_SIZE(mro)>16)return NULL;
    Py_INCREF(mro);
    for(i=0;i<PyTuple_GET_SIZE(mro);i++) {
        PyObject *base=PyTuple_GET_ITEM(mro,i),*space,*value;
        if(!PyType_Check(base))break;
        space=PyType_GetDict((PyTypeObject *)base);if(!space)break;
        value=PyDict_GetItemWithError(space,key);
        if(value)result=Py_NewRef(value);
        Py_DECREF(space);
        if(result||PyErr_Occurred())break;
    }
    Py_DECREF(mro);return result;
}
static int lex_import_admit(LexPlan *p) {
    PyObject *space,*current,*descriptor;int match;
    if(p->guard)return p->guard(p,-1);
    if(!p->import_globals)return 1;
    if(!PyModule_CheckExact(p->import_module)||Py_TYPE(p->import_spec)!=(PyTypeObject *)p->import_spec_type||
        Py_TYPE(p->import_spec)->tp_getattro!=PyObject_GenericGetAttr)return 0;
    space=PyModule_GetDict(p->import_module);
    current=PyDict_GetItemString(space,"__spec__");if(current!=p->import_spec)return 0;
    /* A descriptor or custom getter could run code during the import before
     * the original SDK copies its arguments. Such metadata is unsupported
     * before the native lane imports anything or mutates any SDK slot. */
    descriptor=lex_type_binding(p->import_spec_type,p->initializing);
    if(descriptor){Py_DECREF(descriptor);return 0;}
    if(PyErr_Occurred())return -1;
    space=PyObject_GenericGetDict(p->import_spec,NULL);if(!space)return -1;
    current=PyDict_GetItemWithError(space,p->initializing);match=current==Py_False;
    Py_DECREF(space);return PyErr_Occurred()?-1:match;
}
static int lex_admit(LexPlan *p,int op) {
    PyObject *table=PyTuple_GET_ITEM(p->tables,op);Py_ssize_t i;
    PyTypeObject *cls=(PyTypeObject *)p->cls;
    if(p->guard)return p->guard(p,op);
    if(!lex_owner(p)||cls->tp_mro!=p->mro||cls->tp_getattro!=PyObject_GenericGetAttr||
        cls->tp_setattro!=PyObject_GenericSetAttr)return 0;
    {int imported=lex_import_admit(p);if(imported<=0)return imported;}
    for(i=0;i<PyTuple_GET_SIZE(table);i++) {
        PyObject *row=PyTuple_GET_ITEM(table,i),*owner=PyTuple_GET_ITEM(row,0);
        PyObject *key=PyTuple_GET_ITEM(row,1),*expected=PyTuple_GET_ITEM(row,2),*current=NULL;
        int match;
        if(PyDict_CheckExact(owner)) {
            PyObject *v=PyDict_GetItemWithError(owner,key);if(v)current=Py_NewRef(v);
        } else if(PyFunction_Check(owner))current=Py_NewRef(PyFunction_GetCode(owner));
        else if(PyCell_Check(owner))current=PyCell_Get(owner);
        else current=lex_type_binding(owner,key);
        if(!current)return PyErr_Occurred()?-1:0;
        match=current==expected;Py_DECREF(current);if(!match)return 0;
    }
    return 1;
}
static PyObject *lex_plan_new(PyObject *unused,PyObject *args) {
    PyObject *tables,*cls,*pid_o,*thread_o,*cap_o,*import_globals,*capsule;LexPlan *p=NULL;
    unsigned long long pid,thread,cap;Py_ssize_t op,i;int r;(void)unused;
    const char *names[]={"_raw_paths","_drv","_root","_tail_cached","_str"};
    if(!PyArg_ParseTuple(args,"OOOOOO",&tables,&cls,&pid_o,&thread_o,&cap_o,&import_globals))return NULL;
    r=u64(pid_o,&pid);if(r<=0)goto invalid;r=u64(thread_o,&thread);if(r<=0)goto invalid;
    r=u64(cap_o,&cap);if(r<=0)goto invalid;
    if((import_globals!=Py_None&&!PyDict_CheckExact(import_globals))||
        cap!=256||!PyTuple_CheckExact(tables)||PyTuple_GET_SIZE(tables)!=4||
        !PyType_Check(cls)||Py_TYPE(cls)!=&PyType_Type||strcmp(((PyTypeObject *)cls)->tp_name,"PosixPath")||
        !((PyTypeObject *)cls)->tp_mro||((PyTypeObject *)cls)->tp_dictoffset!=0||
        ((PyTypeObject *)cls)->tp_getattro!=PyObject_GenericGetAttr||
        ((PyTypeObject *)cls)->tp_setattro!=PyObject_GenericSetAttr)goto invalid;
    for(op=0;op<4;op++) {
        PyObject *table=PyTuple_GET_ITEM(tables,op);
        if(!PyTuple_CheckExact(table)||PyTuple_GET_SIZE(table)>128)goto invalid;
        for(i=0;i<PyTuple_GET_SIZE(table);i++) {
            PyObject *row=PyTuple_GET_ITEM(table,i),*owner,*key;
            if(!PyTuple_CheckExact(row)||PyTuple_GET_SIZE(row)!=3)goto invalid;
            owner=PyTuple_GET_ITEM(row,0);key=PyTuple_GET_ITEM(row,1);
            if(!PyUnicode_CheckExact(key)||PyUnicode_GET_LENGTH(key)==0||PyUnicode_GET_LENGTH(key)>128)goto invalid;
            if(PyFunction_Check(owner)) {
                if(PyUnicode_CompareWithASCIIString(key,"__code__"))goto invalid;
            } else if(PyCell_Check(owner)) {
                if(PyUnicode_CompareWithASCIIString(key,"cell_contents"))goto invalid;
            } else if(!PyDict_CheckExact(owner)&&!(PyType_Check(owner)&&Py_TYPE(owner)==&PyType_Type))goto invalid;
        }
    }
    p=PyMem_Calloc(1,sizeof(*p));if(!p)return PyErr_NoMemory();
    p->tables=Py_NewRef(tables);p->cls=Py_NewRef(cls);
    p->mro=Py_NewRef(((PyTypeObject *)cls)->tp_mro);p->pid=pid;p->thread=thread;p->capacity=(Py_ssize_t)cap;
    if(!lex_owner(p))goto invalid;
    p->cache=PyDict_New();p->empty=PyUnicode_FromString("");p->slash=PyUnicode_FromString("/");
    p->double_slash=PyUnicode_FromString("//");p->dot=PyUnicode_FromString(".");
    if(import_globals!=Py_None) {
        PyObject *module=PyDict_GetItemString(PyImport_GetModuleDict(),"ntpath"),*spec;
        if(!module||!PyModule_CheckExact(module))goto invalid;
        spec=PyDict_GetItemString(PyModule_GetDict(module),"__spec__");if(!spec)goto invalid;
        p->import_globals=Py_NewRef(import_globals);p->import_name=PyUnicode_InternFromString("ntpath");
        p->import_module=Py_NewRef(module);p->import_spec=Py_NewRef(spec);
        p->import_spec_type=Py_NewRef((PyObject *)Py_TYPE(spec));p->initializing=PyUnicode_InternFromString("_initializing");
        if(!p->import_name||!p->initializing)goto error;
        r=lex_import_admit(p);if(r<0)goto error;if(!r)goto invalid;
    }
    if(!p->cache||!p->empty||!p->slash||!p->double_slash||!p->dot)goto error;
    for(i=0;i<5;i++){p->names[i]=PyUnicode_InternFromString(names[i]);if(!p->names[i])goto error;}
    if(!lex_owner(p))goto invalid;
    capsule=PyCapsule_New(p,LEX_CAPSULE,lex_destroy);if(!capsule)goto error;
    return capsule;
invalid:
    if(!PyErr_Occurred())PyErr_SetString(PyExc_TypeError,"Invalid lexical code/schema plan");
error:lex_free(p);return NULL;
}
static PyObject *lex_attr(LexPlan *p,PyObject *subject,int slot) {
    PyObject *v=PyObject_GenericGetAttr(subject,p->names[slot]);
    if(!v&&PyErr_ExceptionMatches(PyExc_AttributeError))PyErr_Clear();
    return v;
}
static int lex_strings(PyObject *list,Py_ssize_t *length) {
    Py_ssize_t i,n;
    if(!PyList_CheckExact(list)||(n=PyList_GET_SIZE(list))>64)return 0;
    for(i=0;i<n;i++) {
        PyObject *s=PyList_GET_ITEM(list,i);
        if(!PyUnicode_CheckExact(s)||PyUnicode_GET_LENGTH(s)>8192-*length)return 0;
        *length+=PyUnicode_GET_LENGTH(s);
    }
    return 1;
}
static int lex_old_slots(LexPlan *p,PyObject *subject,int first,int last) {
    int i;
    for(i=first;i<=last;i++) {
        PyObject *v=lex_attr(p,subject,i);Py_ssize_t length=0;int valid;
        if(!v){if(PyErr_Occurred())return -1;continue;}
        valid=(i==0||i==3)?lex_strings(v,&length):PyUnicode_CheckExact(v);
        Py_DECREF(v);if(!valid)return 0;
    }
    return 1;
}
static PyObject *lex_raw(LexPlan *p,PyObject *args) {
    PyObject *list=PyList_New(0);Py_ssize_t i,j,length=0;
    if(!list)return NULL;
    if(PyTuple_GET_SIZE(args)>64)goto unsupported;
    for(i=0;i<PyTuple_GET_SIZE(args);i++) {
        PyObject *arg=PyTuple_GET_ITEM(args,i);
        if(PyUnicode_CheckExact(arg)) {
            if(PyUnicode_GET_LENGTH(arg)>8192-length||PyList_GET_SIZE(list)>=64)goto unsupported;
            length+=PyUnicode_GET_LENGTH(arg);if(PyList_Append(list,arg)<0)goto error;
        } else if(Py_TYPE(arg)==(PyTypeObject *)p->cls) {
            PyObject *raw=lex_attr(p,arg,0);int valid;
            if(!raw){if(PyErr_Occurred())goto error;goto unsupported;}
            valid=lex_strings(raw,&length);
            if(!valid||PyList_GET_SIZE(raw)>64-PyList_GET_SIZE(list)){Py_DECREF(raw);goto unsupported;}
            for(j=0;j<PyList_GET_SIZE(raw);j++)if(PyList_Append(list,PyList_GET_ITEM(raw,j))<0){Py_DECREF(raw);goto error;}
            Py_DECREF(raw);
        } else goto unsupported;
    }
    return list;
unsupported:Py_DECREF(list);Py_RETURN_NOTIMPLEMENTED;
error:Py_DECREF(list);return NULL;
}
static PyObject *lex_join(LexPlan *p,PyObject *raw) {
    PyObject *joined=Py_NewRef(p->empty);Py_ssize_t i;
    for(i=0;i<PyList_GET_SIZE(raw);i++) {
        PyObject *part=PyList_GET_ITEM(raw,i),*next;
        Py_ssize_t n=PyUnicode_GET_LENGTH(joined),m=PyUnicode_GET_LENGTH(part);
        if(m&&PyUnicode_READ_CHAR(part,0)=='/')next=Py_NewRef(part);
        else if(!n||PyUnicode_READ_CHAR(joined,n-1)=='/')next=PyUnicode_Concat(joined,part);
        else {
            PyObject *prefix=PyUnicode_Concat(joined,p->slash);
            if(!prefix){Py_DECREF(joined);return NULL;}
            next=PyUnicode_Concat(prefix,part);Py_DECREF(prefix);
        }
        Py_DECREF(joined);if(!next)return NULL;joined=next;
    }
    return joined;
}
static PyObject *lex_parsed(LexPlan *p,PyObject *path) {
    PyObject *v=PyDict_GetItemWithError(p->cache,path),*split=NULL,*tail=NULL,*value=NULL,*root=p->empty;
    Py_ssize_t i,n=0,size=PyUnicode_GET_LENGTH(path);
    if(v) {
        if(p->hits>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Lexical counter bound");return NULL;}
        p->hits++;return Py_NewRef(v);
    }
    if(PyErr_Occurred())return NULL;
    if(size>8192)Py_RETURN_NOTIMPLEMENTED;
    if(size&&PyUnicode_READ_CHAR(path,0)=='/') {
        root=(size>1&&PyUnicode_READ_CHAR(path,1)=='/'&&(size==2||PyUnicode_READ_CHAR(path,2)!='/'))?
            p->double_slash:p->slash;
    }
    split=PyUnicode_Split(path,p->slash,-1);if(!split)goto error;
    for(i=0;i<PyList_GET_SIZE(split);i++) {
        PyObject *part=PyList_GET_ITEM(split,i);
        if(PyUnicode_GET_LENGTH(part)&&PyUnicode_Compare(part,p->dot))n++;
    }
    if(n>64){Py_DECREF(split);Py_RETURN_NOTIMPLEMENTED;}
    tail=PyTuple_New(n);if(!tail)goto error;n=0;
    for(i=0;i<PyList_GET_SIZE(split);i++) {
        PyObject *part=PyList_GET_ITEM(split,i);
        if(!PyUnicode_GET_LENGTH(part)||!PyUnicode_Compare(part,p->dot))continue;
        part=Py_NewRef(part);PyUnicode_InternInPlace(&part);
        if(!part)goto error;
        PyTuple_SET_ITEM(tail,n++,part);
    }
    value=PyTuple_Pack(2,root,tail);if(!value)goto error;
    if(PyDict_Size(p->cache)>=p->capacity) {
        Py_ssize_t pos=0;PyObject *key,*item;
        if(PyDict_Next(p->cache,&pos,&key,&item)) {
            key=Py_NewRef(key);i=PyDict_DelItem(p->cache,key);Py_DECREF(key);if(i<0)goto error;
        }
    }
    if(p->misses>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Lexical counter bound");goto error;}
    if(PyDict_SetItem(p->cache,path,value)<0)goto error;
    p->misses++;Py_DECREF(split);Py_DECREF(tail);return value;
error:Py_XDECREF(split);Py_XDECREF(tail);Py_XDECREF(value);return NULL;
}
static PyObject *lex_parts(LexPlan *p,PyObject *subject) {
    PyObject *raw=lex_attr(p,subject,0),*path,*parsed;Py_ssize_t length=0;
    if(!raw){if(PyErr_Occurred())return NULL;Py_RETURN_NOTIMPLEMENTED;}
    if(!lex_strings(raw,&length)){Py_DECREF(raw);Py_RETURN_NOTIMPLEMENTED;}
    path=lex_join(p,raw);Py_DECREF(raw);if(!path)return NULL;
    parsed=lex_parsed(p,path);Py_DECREF(path);return parsed;
}
static int lex_store_parts(LexPlan *p,PyObject *subject,PyObject *parsed) {
    PyObject *tail=PySequence_List(PyTuple_GET_ITEM(parsed,1));int r;
    if(!tail)return -1;
    r=PyObject_GenericSetAttr(subject,p->names[1],p->empty);
    if(r==0)r=PyObject_GenericSetAttr(subject,p->names[2],PyTuple_GET_ITEM(parsed,0));
    if(r==0)r=PyObject_GenericSetAttr(subject,p->names[3],tail);
    Py_DECREF(tail);return r;
}
static PyObject *lex_load(LexPlan *p,PyObject *subject) {
    PyObject *parsed;int r=lex_old_slots(p,subject,1,3);
    if(r<0)return NULL;
    if(!r)Py_RETURN_NOTIMPLEMENTED;
    parsed=lex_parts(p,subject);if(!parsed||parsed==Py_NotImplemented)return parsed;
    r=lex_store_parts(p,subject,parsed);Py_DECREF(parsed);if(r<0)return NULL;
    Py_RETURN_NONE;
}
static PyObject *lex_string(LexPlan *p,PyObject *subject) {
    PyObject *cached=lex_attr(p,subject,4),*drv=NULL,*root=NULL,*tail=NULL,*joined=NULL,*result=NULL;
    Py_ssize_t length=0;int missing;
    if(cached)return cached;
    if(PyErr_Occurred())return NULL;
    drv=lex_attr(p,subject,1);if(PyErr_Occurred())goto error;
    root=lex_attr(p,subject,2);if(PyErr_Occurred())goto error;
    tail=lex_attr(p,subject,3);if(PyErr_Occurred())goto error;
    missing=(!drv)+(!root)+(!tail);
    if(missing&&missing!=3)goto unsupported;
    if(missing==3) {
        PyObject *parsed=lex_parts(p,subject);
        if(!parsed)goto error;
        if(parsed==Py_NotImplemented){Py_DECREF(parsed);goto unsupported;}
        if(lex_store_parts(p,subject,parsed)<0){Py_DECREF(parsed);goto error;}
        drv=Py_NewRef(p->empty);root=Py_NewRef(PyTuple_GET_ITEM(parsed,0));
        tail=PySequence_List(PyTuple_GET_ITEM(parsed,1));Py_DECREF(parsed);if(!tail)goto error;
    }
    if(!PyUnicode_CheckExact(drv)||PyUnicode_GET_LENGTH(drv)||!PyUnicode_CheckExact(root)||!lex_strings(tail,&length))goto unsupported;
    joined=PyUnicode_Join(p->slash,tail);if(!joined)goto error;
    result=PyUnicode_Concat(root,joined);if(!result)goto error;
    if(!PyUnicode_GET_LENGTH(result))Py_SETREF(result,Py_NewRef(p->dot));
    if(PyObject_GenericSetAttr(subject,p->names[4],result)<0){Py_CLEAR(result);goto error;}
    Py_DECREF(drv);Py_DECREF(root);Py_DECREF(tail);Py_DECREF(joined);return result;
unsupported:Py_XDECREF(drv);Py_XDECREF(root);Py_XDECREF(tail);Py_RETURN_NOTIMPLEMENTED;
error:Py_XDECREF(drv);Py_XDECREF(root);Py_XDECREF(tail);Py_XDECREF(joined);Py_XDECREF(result);return NULL;
}
static PyObject *lex_execute(LexPlan *p,int op,PyObject *subject,PyObject *arguments) {
    PyObject *value=NULL,*pending,*imported=NULL;int r;
    /* The descriptor guard below includes fresh ownership before any SDK slot
     * read/mutation or import. Avoid querying that same owner twice before
     * computation; keep legacy admission and every post/import check. */
    if(!p->guard&&!lex_owner(p)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if(p->broken){PyErr_SetString(PyExc_ValueError,"Poisoned lexical plan");return NULL;}
    if(Py_TYPE(subject)!=(PyTypeObject *)p->cls)Py_RETURN_NOTIMPLEMENTED;
    r=lex_admit(p,(int)op);if(r<0)return NULL;if(!r)Py_RETURN_NOTIMPLEMENTED;
    if(p->calls[op]>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Lexical counter bound");return NULL;}
    if((op==1||op==2)&&PyTuple_GET_SIZE(arguments))Py_RETURN_NOTIMPLEMENTED;
    if(op==0||op==3) {
        PyObject *raw=lex_raw(p,arguments);
        if(!raw||raw==Py_NotImplemented)return raw;
        if(op==0) {
            r=lex_old_slots(p,subject,0,0);
            if(r<0){Py_DECREF(raw);return NULL;}
            if(!r){Py_DECREF(raw);Py_RETURN_NOTIMPLEMENTED;}
        }
        /* Match Ubuntu's actual constructor-local IMPORT_NAME, including its
         * current module lookup. The captured globals are code context only;
         * no import result is retained. Changed import hooks fall back at the
         * fresh admission above, before any import or SDK-slot mutation. */
        if(p->import_globals) {
            r=lex_import_admit(p);
            if(r<=0){Py_DECREF(raw);if(r<0)return NULL;Py_RETURN_NOTIMPLEMENTED;}
            imported=PyImport_ImportModuleLevelObject(p->import_name,p->import_globals,p->import_globals,Py_None,0);
            if(!imported){Py_DECREF(raw);goto complete;}
        }
        if(op==0) {
            r=PyObject_GenericSetAttr(subject,p->names[0],raw);
            if(r==0)value=Py_NewRef(Py_None);
        } else {
            value=PyType_GenericAlloc((PyTypeObject *)p->cls,0);
            if(value&&PyObject_GenericSetAttr(value,p->names[0],raw)<0)Py_CLEAR(value);
        }
        Py_DECREF(raw);
    } else if(op==1)value=lex_load(p,subject);
    else value=lex_string(p,subject);
complete:
    pending=PyErr_GetRaisedException();r=lex_admit(p,(int)op);Py_XDECREF(imported);
    if(r<=0){p->broken=1;PyDict_Clear(p->cache);}
    if(pending) {
        PyErr_Clear();PyErr_SetRaisedException(pending);Py_XDECREF(value);return NULL;
    }
    if(r<=0) {
        Py_XDECREF(value);
        if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"Lexical bindings changed during computation");
        return NULL;
    }
    if(value&&value!=Py_NotImplemented)p->calls[op]++;
    return value;
}
static PyObject *lex_path_call(PyObject *unused,PyObject *args) {
    PyObject *op_o,*capsule,*subject,*arguments;LexPlan *p;unsigned long long op;int r;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOO",&op_o,&capsule,&subject,&arguments))return NULL;
    r=u64(op_o,&op);if(r<=0||op>5||!PyTuple_CheckExact(arguments))goto invalid;
    p=PyCapsule_GetPointer(capsule,LEX_CAPSULE);if(!p)return NULL;
    if(op>=4) {
        if(subject!=Py_None||PyTuple_GET_SIZE(arguments))goto invalid;
        if(!lex_owner(p)){PyErr_SetString(PyExc_ValueError,"Lexical owner changed");return NULL;}
        if(op==4)return Py_BuildValue("{sK,sK,sK,sK,sn,sK,sK}",
            "constructor",p->calls[0],"load_parts",p->calls[1],"string",p->calls[2],"with_segments",p->calls[3],
            "cache_entries",PyDict_Size(p->cache),"cache_hits",p->hits,"cache_misses",p->misses);
        PyDict_Clear(p->cache);Py_RETURN_NONE;
    }
    return lex_execute(p,(int)op,subject,arguments);
invalid:if(!PyErr_Occurred())PyErr_SetString(PyExc_TypeError,"Invalid lexical operation");return NULL;
}
/* C-bound SDK methods. Notifications retain only negative code-input
 * invalidation; every call also checks current function/type/owner fields.
 * No file, process, database, Root admission or observation is cached here.
 * https://docs.python.org/3.12/c-api/dict.html#c.PyDict_AddWatcher
 * https://docs.python.org/3.12/c-api/method.html#c.PyInstanceMethod_New */
#define DESC_CAPSULE "_native_metadata_probe.descriptor_plan.v1"
#define DESC_BOUND 256
typedef struct {PyObject *space,*keys;} DescWatch;
typedef struct {
    PyObject *fn,*code,*globals,*builtins,*closure,*defaults,*kwdefaults,*kwitems;
    vectorcallfunc vectorcall;
} DescFunction;
typedef struct {
    PyObject *cls,*mro,*meta;
    getattrofunc get;setattrofunc set;newfunc new;allocfunc alloc;
    destructor dealloc,del,finalize;
} DescType;
typedef struct {PyObject *cell,*value;} DescCell;
typedef struct {
    PyObject *lexical,*originals,*modules,*empty_args,*spec_dict;
    LexPlan *lex;PyInterpreterState *interpreter;
    DescWatch watched[DESC_BOUND];DescFunction functions[DESC_BOUND];
    DescType types[DESC_BOUND];DescCell cells[DESC_BOUND];
    Py_ssize_t nwatch,nfunction,ntype,ncell,nstarted;
    unsigned long long entries[4],fallbacks[4];
    unsigned long long role_prepares[8],role_calls[8];
    unsigned long long absolute_imports;
    int issued,bound,active,closed,dirty,watcher;
    int role_configured,absolute_import;
} DescriptorPlan;
/* One scope on the main interpreter. A failed/nested activation never replaces
 * this pointer. It is cleared only after all notifications are unregistered. */
static DescriptorPlan *descriptor_active=NULL;

static int desc_name_equal(PyObject *a,PyObject *b) {
    Py_ssize_t i,n=PyUnicode_GET_LENGTH(a);
    if(n!=PyUnicode_GET_LENGTH(b))return 0;
    for(i=0;i<n;i++)if(PyUnicode_READ(PyUnicode_KIND(a),PyUnicode_DATA(a),i)!=
        PyUnicode_READ(PyUnicode_KIND(b),PyUnicode_DATA(b),i))return 0;
    return 1;
}
static int desc_notification(PyDict_WatchEvent event,PyObject *space,PyObject *key,PyObject *value) {
    DescriptorPlan *p=descriptor_active;Py_ssize_t i,j;(void)value;
    /* No allocation, Python, I/O or error API: an existing exception is
     * untouched, including callbacks during interrupted import/cleanup. */
    if(!p||p->dirty||PyInterpreterState_Get()!=p->interpreter)return 0;
    for(i=0;i<p->nwatch;i++)if(p->watched[i].space==space) {
        if(event!=PyDict_EVENT_ADDED&&event!=PyDict_EVENT_MODIFIED&&event!=PyDict_EVENT_DELETED) {
            p->dirty=1;return 0;
        }
        if(!key||!PyUnicode_CheckExact(key)){p->dirty=1;return 0;}
        for(j=0;j<PyList_GET_SIZE(p->watched[i].keys);j++)
            if(PyList_GET_ITEM(p->watched[i].keys,j)==Py_None){p->dirty=1;return 0;}
        for(j=0;j<PyList_GET_SIZE(p->watched[i].keys);j++)
            if(desc_name_equal(key,PyList_GET_ITEM(p->watched[i].keys,j))){p->dirty=1;return 0;}
        return 0;
    }
    return 0;
}
static int desc_stop(DescriptorPlan *p) {
    PyObject *failure=NULL;Py_ssize_t i;
    p->active=0;
    if(p->watcher<0)return 0;
    for(i=0;i<p->nstarted;i++)if(PyDict_Unwatch(p->watcher,p->watched[i].space)<0) {
        PyObject *e=PyErr_GetRaisedException();if(!failure)failure=e;else Py_XDECREF(e);
    }
    if(PyDict_ClearWatcher(p->watcher)<0) {
        PyObject *e=PyErr_GetRaisedException();if(!failure)failure=e;else Py_XDECREF(e);
    }
    p->watcher=-1;p->nstarted=0;
    if(descriptor_active==p)descriptor_active=NULL;
    if(failure){p->dirty=1;PyErr_SetRaisedException(failure);return -1;}
    return 0;
}
static void desc_release_schema(DescriptorPlan *p) {
    Py_ssize_t i;
    for(i=0;i<p->nwatch;i++){Py_CLEAR(p->watched[i].space);Py_CLEAR(p->watched[i].keys);}
    for(i=0;i<p->nfunction;i++) {
        DescFunction *f=&p->functions[i];
        Py_CLEAR(f->fn);Py_CLEAR(f->code);Py_CLEAR(f->globals);Py_CLEAR(f->builtins);Py_CLEAR(f->closure);
        Py_CLEAR(f->defaults);Py_CLEAR(f->kwdefaults);Py_CLEAR(f->kwitems);
    }
    for(i=0;i<p->ntype;i++){Py_CLEAR(p->types[i].cls);Py_CLEAR(p->types[i].mro);Py_CLEAR(p->types[i].meta);}
    for(i=0;i<p->ncell;i++){Py_CLEAR(p->cells[i].cell);Py_CLEAR(p->cells[i].value);}
    p->nwatch=p->nfunction=p->ntype=p->ncell=0;
    Py_CLEAR(p->modules);Py_CLEAR(p->spec_dict);
    if(p->lex)Py_CLEAR(p->lex->tables);
}
static void desc_destroy(PyObject *capsule) {
    PyObject *pending=PyErr_GetRaisedException();
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);
    if(p) {
        if(desc_stop(p)<0)PyErr_Clear();
        desc_release_schema(p);
        if(p->lex){p->lex->guard=NULL;p->lex->code_context=NULL;}
        Py_XDECREF(p->lexical);Py_XDECREF(p->originals);Py_XDECREF(p->empty_args);PyMem_Free(p);
    } else PyErr_Clear();
    PyErr_SetRaisedException(pending);
}
static int desc_owner(DescriptorPlan *p) {
    return PyInterpreterState_Get()==p->interpreter&&lex_owner(p->lex);
}
static int desc_add_watch(DescriptorPlan *p,PyObject *space,PyObject *key) {
    Py_ssize_t i,j;DescWatch *w;
    if(!PyDict_CheckExact(space)||(key!=Py_None&&!PyUnicode_CheckExact(key)))goto invalid;
    for(i=0;i<p->nwatch;i++)if(p->watched[i].space==space)break;
    if(i==p->nwatch) {
        if(i>=DESC_BOUND)goto invalid;
        w=&p->watched[p->nwatch++];w->space=Py_NewRef(space);w->keys=PyList_New(0);
        if(!w->keys)return -1;
    } else w=&p->watched[i];
    for(j=0;j<PyList_GET_SIZE(w->keys);j++) {
        PyObject *old=PyList_GET_ITEM(w->keys,j);
        if(old==key||(old!=Py_None&&key!=Py_None&&desc_name_equal(key,old)))return 0;
    }
    if(PyList_GET_SIZE(w->keys)>=DESC_BOUND)goto invalid;
    return PyList_Append(w->keys,key);
invalid:PyErr_SetString(PyExc_TypeError,"Invalid descriptor namespace schema");return -1;
}
static int desc_add_type(DescriptorPlan *p,PyObject *cls) {
    Py_ssize_t i;DescType *t;PyTypeObject *c=(PyTypeObject *)cls;
    for(i=0;i<p->ntype;i++)if(p->types[i].cls==cls)return 0;
    if(p->ntype>=DESC_BOUND||!PyType_Check(cls)||
        !c->tp_mro||!PyTuple_CheckExact(c->tp_mro)||PyTuple_GET_SIZE(c->tp_mro)>16) {
        PyErr_SetString(PyExc_TypeError,"Invalid descriptor type schema");return -1;
    }
    t=&p->types[p->ntype++];t->cls=Py_NewRef(cls);t->mro=Py_NewRef(c->tp_mro);
    t->meta=Py_NewRef((PyObject *)Py_TYPE(cls));
    t->get=c->tp_getattro;t->set=c->tp_setattro;t->new=c->tp_new;t->alloc=c->tp_alloc;
    t->dealloc=c->tp_dealloc;t->del=c->tp_del;t->finalize=c->tp_finalize;return 0;
}
static int desc_add_function(DescriptorPlan *p,PyObject *fn) {
    Py_ssize_t i,j;DescFunction *f;PyFunctionObject *v=(PyFunctionObject *)fn;
    for(i=0;i<p->nfunction;i++)if(p->functions[i].fn==fn)return 0;
    if(p->nfunction>=DESC_BOUND||!PyFunction_Check(fn)) {
        PyErr_SetString(PyExc_TypeError,"Invalid descriptor function schema");return -1;
    }
    f=&p->functions[p->nfunction++];f->fn=Py_NewRef(fn);f->code=Py_NewRef(v->func_code);
    f->globals=Py_NewRef(v->func_globals);f->builtins=Py_NewRef(v->func_builtins);
    f->closure=Py_XNewRef(v->func_closure);f->vectorcall=v->vectorcall;
    f->defaults=Py_XNewRef(v->func_defaults);f->kwdefaults=Py_XNewRef(v->func_kwdefaults);
    if(f->defaults) {
        if(!PyTuple_CheckExact(f->defaults)||PyTuple_GET_SIZE(f->defaults)>16)goto invalid;
        for(j=0;j<PyTuple_GET_SIZE(f->defaults);j++) {
            PyObject *d=PyTuple_GET_ITEM(f->defaults,j);
            if(d!=Py_None&&!PyBool_Check(d)&&!PyLong_CheckExact(d)&&!PyUnicode_CheckExact(d))goto invalid;
        }
    }
    if(f->kwdefaults) {
        if(!PyDict_CheckExact(f->kwdefaults)||PyDict_Size(f->kwdefaults)>16)goto invalid;
        f->kwitems=PyDict_Items(f->kwdefaults);if(!f->kwitems)return -1;
        for(j=0;j<PyList_GET_SIZE(f->kwitems);j++) {
            PyObject *row=PyList_GET_ITEM(f->kwitems,j),*d=PyTuple_GET_ITEM(row,1);
            if(!PyUnicode_CheckExact(PyTuple_GET_ITEM(row,0))||
                (d!=Py_None&&!PyBool_Check(d)&&!PyLong_CheckExact(d)&&!PyUnicode_CheckExact(d)))goto invalid;
        }
        if(desc_add_watch(p,f->kwdefaults,Py_None)<0)return -1;
    }
    return 0;
invalid:PyErr_SetString(PyExc_TypeError,"Mutable or unsupported code defaults");return -1;
}
static int desc_direct(DescriptorPlan *p) {
    Py_ssize_t i;
    if(!desc_owner(p)||p->dirty||p->closed||p->lex->broken)return 0;
    for(i=0;i<PyTuple_GET_SIZE(p->modules);i++)if(!PyModule_CheckExact(PyTuple_GET_ITEM(p->modules,i)))goto changed;
    for(i=0;i<p->ntype;i++) {
        DescType *t=&p->types[i];PyTypeObject *c=(PyTypeObject *)t->cls;
        if((PyObject *)Py_TYPE(c)!=t->meta||c->tp_mro!=t->mro||c->tp_getattro!=t->get||
            c->tp_setattro!=t->set||c->tp_new!=t->new||c->tp_alloc!=t->alloc||
            c->tp_dealloc!=t->dealloc||c->tp_del!=t->del||c->tp_finalize!=t->finalize)goto changed;
    }
    for(i=0;i<p->nfunction;i++) {
        DescFunction *f=&p->functions[i];PyFunctionObject *v=(PyFunctionObject *)f->fn;
        if(v->func_code!=f->code||v->func_globals!=f->globals||v->func_builtins!=f->builtins||
            v->func_defaults!=f->defaults||v->func_kwdefaults!=f->kwdefaults||v->func_closure!=f->closure||v->vectorcall!=f->vectorcall)goto changed;
        if(f->kwdefaults) {
            Py_ssize_t j;
            if(PyDict_Size(f->kwdefaults)!=PyList_GET_SIZE(f->kwitems))goto changed;
            for(j=0;j<PyList_GET_SIZE(f->kwitems);j++) {
                PyObject *row=PyList_GET_ITEM(f->kwitems,j),*value=PyDict_GetItemWithError(f->kwdefaults,PyTuple_GET_ITEM(row,0));
                if(PyErr_Occurred())return -1;
                if(value!=PyTuple_GET_ITEM(row,1))goto changed;
            }
        }
    }
    for(i=0;i<p->ncell;i++)if(PyCell_GET(p->cells[i].cell)!=p->cells[i].value)goto changed;
    if(p->lex->import_globals) {
        PyObject *space;
        if(Py_TYPE(p->lex->import_spec)!=(PyTypeObject *)p->lex->import_spec_type)goto changed;
        space=PyObject_GenericGetDict(p->lex->import_spec,NULL);
        if(!space)return -1;
        i=space==p->spec_dict;Py_DECREF(space);if(!i)goto changed;
    }
    return 1;
changed:p->dirty=1;return 0;
}
static int desc_admit(LexPlan *lex,int op) {
    DescriptorPlan *p=lex->code_context;(void)op;
    if(!p||!p->active||p->watcher<0)return 0;
    return desc_direct(p);
}
static PyObject *descriptor_plan(PyObject *unused,PyObject *args) {
    PyObject *cls,*originals,*pid,*thread,*capacity,*import_globals,*tables=NULL,*a=NULL,*capsule;
    DescriptorPlan *p=NULL;Py_ssize_t i;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOOOO",&cls,&originals,&pid,&thread,&capacity,&import_globals))return NULL;
    if(PyInterpreterState_Get()!=PyInterpreterState_Main()||!PyTuple_CheckExact(originals)||PyTuple_GET_SIZE(originals)!=4)goto invalid;
    for(i=0;i<4;i++)if(!PyFunction_Check(PyTuple_GET_ITEM(originals,i)))goto invalid;
    p=PyMem_Calloc(1,sizeof(*p));if(!p)return PyErr_NoMemory();p->watcher=-1;
    p->interpreter=PyInterpreterState_Get();p->originals=Py_NewRef(originals);p->empty_args=PyTuple_New(0);
    if(!p->empty_args)goto error;
    tables=PyTuple_Pack(4,p->empty_args,p->empty_args,p->empty_args,p->empty_args);if(!tables)goto error;
    a=PyTuple_Pack(6,tables,cls,pid,thread,capacity,import_globals);if(!a)goto error;
    p->lexical=lex_plan_new(NULL,a);if(!p->lexical)goto error;
    p->lex=PyCapsule_GetPointer(p->lexical,LEX_CAPSULE);if(!p->lex)goto error;
    p->lex->code_context=p;p->lex->guard=desc_admit;
    capsule=PyCapsule_New(p,DESC_CAPSULE,desc_destroy);if(!capsule)goto error;
    Py_DECREF(a);Py_DECREF(tables);return capsule;
invalid:PyErr_SetString(PyExc_TypeError,"Invalid bound lexical context");
error:
    Py_XDECREF(a);Py_XDECREF(tables);
    if(p){Py_XDECREF(p->lexical);Py_XDECREF(p->originals);Py_XDECREF(p->empty_args);PyMem_Free(p);}
    return NULL;
}
static PyObject *desc_invoke(PyObject *capsule,PyObject *const *args,Py_ssize_t nargs,PyObject *keywords,int op) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);PyObject *arguments,*value;Py_ssize_t i;
    if(!p)return NULL;
    if(p->entries[op]>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Descriptor counter bound");return NULL;}
    p->entries[op]++;
    if(!p->closed&&p->active&&!p->dirty&&!p->lex->broken&&nargs>0&&(!keywords||!PyTuple_GET_SIZE(keywords))) {
        if(nargs==1)arguments=Py_NewRef(p->empty_args);
        else {
            arguments=PyTuple_New(nargs-1);if(!arguments)return NULL;
            for(i=1;i<nargs;i++)PyTuple_SET_ITEM(arguments,i-1,Py_NewRef(args[i]));
        }
        value=lex_execute(p->lex,op,args[0],arguments);Py_DECREF(arguments);
        if(!value||value!=Py_NotImplemented)return value;
        Py_DECREF(value);
    }
    if(p->fallbacks[op]>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Descriptor counter bound");return NULL;}
    p->fallbacks[op]++;
    return PyObject_Vectorcall(PyTuple_GET_ITEM(p->originals,op),args,(size_t)nargs,keywords);
}
#define DESC_METHOD(fn,op) \
    static PyObject *fn(PyObject *self,PyObject *const *args,Py_ssize_t nargs,PyObject *kw) \
    {return desc_invoke(self,args,nargs,kw,op);}
DESC_METHOD(desc_constructor,0)
DESC_METHOD(desc_load_parts,1)
DESC_METHOD(desc_string,2)
DESC_METHOD(desc_with_segments,3)
static PyMethodDef descriptor_methods[]={
    {"__init__",_PyCFunction_CAST(desc_constructor),METH_FASTCALL|METH_KEYWORDS,NULL},
    {"_load_parts",_PyCFunction_CAST(desc_load_parts),METH_FASTCALL|METH_KEYWORDS,NULL},
    {"__str__",_PyCFunction_CAST(desc_string),METH_FASTCALL|METH_KEYWORDS,NULL},
    {"with_segments",_PyCFunction_CAST(desc_with_segments),METH_FASTCALL|METH_KEYWORDS,NULL}
};
static PyObject *descriptor_entries(PyObject *unused,PyObject *capsule) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);PyObject *result,*module;int i;(void)unused;
    if(!p)return NULL;
    if(!desc_owner(p)||p->issued||p->closed){PyErr_SetString(PyExc_ValueError,"Descriptor entries unavailable");return NULL;}
    p->issued=1;result=PyTuple_New(4);if(!result)return NULL;
    module=PyUnicode_FromString("pathlib");if(!module){Py_DECREF(result);return NULL;}
    for(i=0;i<4;i++) {
        PyObject *fn=PyCFunction_NewEx(&descriptor_methods[i],capsule,module),*method;
        if(!fn)goto error;
        method=PyInstanceMethod_New(fn);Py_DECREF(fn);if(!method)goto error;
        PyTuple_SET_ITEM(result,i,method);
    }
    Py_DECREF(module);return result;
error:Py_DECREF(module);Py_DECREF(result);return NULL;
}
static PyObject *descriptor_bind(PyObject *unused,PyObject *args) {
    PyObject *capsule,*tables,*modules,*table;DescriptorPlan *p;Py_ssize_t i,j,k;(void)unused;
    if(!PyArg_ParseTuple(args,"OOO",&capsule,&tables,&modules))return NULL;
    p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);if(!p)return NULL;
    if(!desc_owner(p)||p->closed||!p->issued||p->bound)goto invalid;
    p->bound=-1; /* A partial schema can only be closed, never rebound. */
    if(!PyTuple_CheckExact(tables)||PyTuple_GET_SIZE(tables)!=4||!PyTuple_CheckExact(modules)||
        PyTuple_GET_SIZE(modules)==0||PyTuple_GET_SIZE(modules)>16)goto invalid;
    table=PyTuple_GET_ITEM(tables,0);
    if(!PyTuple_CheckExact(table)||PyTuple_GET_SIZE(table)==0||PyTuple_GET_SIZE(table)>512)goto invalid;
    for(i=1;i<4;i++) {
        PyObject *other=PyTuple_GET_ITEM(tables,i);
        if(!PyTuple_CheckExact(other)||PyTuple_GET_SIZE(other)!=PyTuple_GET_SIZE(table))goto invalid;
        for(j=0;j<PyTuple_GET_SIZE(table);j++)if(PyTuple_GET_ITEM(other,j)!=PyTuple_GET_ITEM(table,j))goto invalid;
    }
    for(i=0;i<PyTuple_GET_SIZE(modules);i++)if(!PyModule_CheckExact(PyTuple_GET_ITEM(modules,i)))goto invalid;
    p->modules=Py_NewRef(modules);Py_SETREF(p->lex->tables,Py_NewRef(tables));
    for(i=0;i<PyTuple_GET_SIZE(table);i++) {
        PyObject *row=PyTuple_GET_ITEM(table,i),*owner,*key;
        if(!PyTuple_CheckExact(row)||PyTuple_GET_SIZE(row)!=3)goto invalid;
        owner=PyTuple_GET_ITEM(row,0);key=PyTuple_GET_ITEM(row,1);
        if(!PyUnicode_CheckExact(key)||!PyUnicode_GET_LENGTH(key)||PyUnicode_GET_LENGTH(key)>128)goto invalid;
        if(PyDict_CheckExact(owner)) {if(desc_add_watch(p,owner,key)<0)return NULL;}
        else if(PyFunction_Check(owner)) {
            if(PyUnicode_CompareWithASCIIString(key,"__code__"))goto invalid;
            if(desc_add_function(p,owner)<0)return NULL;
        } else if(PyCell_Check(owner)) {
            DescCell *cell;
            if(PyUnicode_CompareWithASCIIString(key,"cell_contents")||p->ncell>=DESC_BOUND)goto invalid;
            cell=&p->cells[p->ncell++];cell->cell=Py_NewRef(owner);cell->value=Py_NewRef(PyTuple_GET_ITEM(row,2));
        } else if(PyType_Check(owner)) {
            PyObject *mro=((PyTypeObject *)owner)->tp_mro;
            if(!mro||!PyTuple_CheckExact(mro)||PyTuple_GET_SIZE(mro)>16)goto invalid;
            for(j=0;j<PyTuple_GET_SIZE(mro);j++) {
                PyObject *base=PyTuple_GET_ITEM(mro,j),*space,*hook;int h;
                const char *hooks[]={"__getattr__","__del__"};
                if(desc_add_type(p,base)<0)return NULL;
                space=PyType_GetDict((PyTypeObject *)base);if(!space)return NULL;
                k=desc_add_watch(p,space,key);if(k<0){Py_DECREF(space);return NULL;}
                for(h=0;h<2;h++) {
                    hook=PyUnicode_InternFromString(hooks[h]);if(!hook){Py_DECREF(space);return NULL;}
                    k=desc_add_watch(p,space,hook);Py_DECREF(hook);if(k<0){Py_DECREF(space);return NULL;}
                }
                Py_DECREF(space);
            }
        } else goto invalid;
    }
    if(p->lex->import_globals) {
        PyObject *spec=p->lex->import_spec,*type=p->lex->import_spec_type;
        PyObject *mro=((PyTypeObject *)type)->tp_mro,*space,*key;
        const char *hooks[]={"_initializing","__getattribute__","__getattr__","__dict__","__del__"};
        p->spec_dict=PyObject_GenericGetDict(spec,NULL);if(!p->spec_dict)return NULL;
        if(desc_add_watch(p,p->spec_dict,p->lex->initializing)<0)return NULL;
        key=PyUnicode_InternFromString("__spec__");if(!key)return NULL;
        k=desc_add_watch(p,PyModule_GetDict(p->lex->import_module),key);Py_DECREF(key);if(k<0)return NULL;
        if(!mro||!PyTuple_CheckExact(mro)||PyTuple_GET_SIZE(mro)>16)goto invalid;
        for(i=0;i<PyTuple_GET_SIZE(mro);i++) {
            PyObject *base=PyTuple_GET_ITEM(mro,i);if(desc_add_type(p,base)<0)return NULL;
            space=PyType_GetDict((PyTypeObject *)base);if(!space)return NULL;
            for(j=0;j<5;j++) {
                key=PyUnicode_InternFromString(hooks[j]);if(!key){Py_DECREF(space);return NULL;}
                k=desc_add_watch(p,space,key);Py_DECREF(key);if(k<0){Py_DECREF(space);return NULL;}
            }
            Py_DECREF(space);
        }
    }
    if(p->nwatch+p->nfunction+p->ntype+p->ncell>DESC_BOUND)goto invalid;
    p->bound=1;Py_RETURN_NONE;
invalid:if(!PyErr_Occurred())PyErr_SetString(PyExc_TypeError,"Invalid bound lexical schema");return NULL;
}
static PyObject *descriptor_phase(PyObject *unused,PyObject *args) {
    PyObject *capsule,*phase_o;DescriptorPlan *p;unsigned long long phase;int r;Py_ssize_t i;(void)unused;
    if(!PyArg_ParseTuple(args,"OO",&capsule,&phase_o))return NULL;
    r=u64(phase_o,&phase);if(r<=0||phase>1)goto invalid;
    p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);if(!p)return NULL;
    if(!desc_owner(p)||p->closed||(phase!=0&&phase!=1))goto invalid;
    if(phase==1){if(desc_stop(p)<0)return NULL;Py_RETURN_NONE;}
    if(p->active||p->bound!=1||descriptor_active)goto invalid;
    p->dirty=0;
    p->watcher=PyDict_AddWatcher(desc_notification);if(p->watcher<0)return NULL;
    descriptor_active=p;
    for(i=0;i<p->nwatch;i++) {
        if(PyDict_Watch(p->watcher,p->watched[i].space)<0)goto failure;
        p->nstarted++;
    }
    /* Full original namespace/MRO admission at each activation, after the
     * notifications are installed and before native handling can begin. */
    p->lex->guard=NULL;r=lex_admit(p->lex,0);p->lex->guard=desc_admit;
    if(r<0)goto failure;
    if(!r)goto refused;
    r=desc_direct(p);if(r<0)goto failure;if(!r)goto refused;
    p->active=1;Py_RETURN_NONE;
refused:PyErr_SetString(PyExc_ValueError,"Bound lexical code inputs changed");
failure: {
        PyObject *pending=PyErr_GetRaisedException();p->dirty=1;
        if(desc_stop(p)<0)PyErr_Clear();
        PyErr_SetRaisedException(pending);return NULL;
    }
invalid:PyErr_SetString(PyExc_ValueError,"Invalid bound lexical phase");return NULL;
}
static PyObject *descriptor_counts(PyObject *unused,PyObject *capsule) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);const char *phase;(void)unused;
    if(!p)return NULL;
    if(!desc_owner(p)){PyErr_SetString(PyExc_ValueError,"Descriptor owner changed");return NULL;}
    phase=p->closed?"closed":p->active?"active":p->bound==1?"inactive":"prepared";
    return Py_BuildValue("{s:{sK,sK,sK,sK},s:{sK,sK,sK,sK},s:{sK,sK,sK,sK},sn,sK,sK,ss,sO,sO,sn}",
        "calls","constructor",p->lex->calls[0],"load_parts",p->lex->calls[1],"string",p->lex->calls[2],"with_segments",p->lex->calls[3],
        "entries","constructor",p->entries[0],"load_parts",p->entries[1],"string",p->entries[2],"with_segments",p->entries[3],
        "fallbacks","constructor",p->fallbacks[0],"load_parts",p->fallbacks[1],"string",p->fallbacks[2],"with_segments",p->fallbacks[3],
        "cache_entries",PyDict_Size(p->lex->cache),"cache_hits",p->lex->hits,"cache_misses",p->lex->misses,
        "phase",phase,"watching",p->watcher>=0?Py_True:Py_False,"code_changed",p->dirty?Py_True:Py_False,
        "code_inputs",p->nwatch+p->nfunction+p->ntype+p->ncell);
}
static PyObject *descriptor_close(PyObject *unused,PyObject *capsule) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);(void)unused;
    if(!p)return NULL;
    if(!desc_owner(p)||p->active){PyErr_SetString(PyExc_ValueError,"Cannot close active descriptor context");return NULL;}
    if(!p->closed) {
        if(desc_stop(p)<0)return NULL;
        p->closed=1;PyDict_Clear(p->lex->cache);desc_release_schema(p);
    }
    Py_RETURN_NONE;
}

/* Lexical preparation inside a single admitted observation role. These helpers
 * retain only immutable parsed strings/tuples; observations remain in the
 * original eight implementations above. SDK descriptors are never installed. */
static PyObject *role_configure(PyObject *unused,PyObject *args) {
    PyObject *capsule,*absolute;DescriptorPlan *p;(void)unused;
    if(!PyArg_ParseTuple(args,"OO",&capsule,&absolute))return NULL;
    p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);if(!p)return NULL;
    if(!desc_owner(p)||!p->issued||p->closed||p->bound||p->role_configured||
        !PyBool_Check(absolute)||(absolute==Py_True&&!p->lex->import_globals)) {
        PyErr_SetString(PyExc_ValueError,"Invalid complete role configuration");return NULL;
    }
    p->absolute_import=absolute==Py_True;p->role_configured=1;Py_RETURN_NONE;
}
static int role_absolute_import(DescriptorPlan *p) {
    PyObject *module;int r;
    if(!p->absolute_import)return 0;
    if(p->absolute_imports>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Absolute import bound");return -1;}
    r=lex_import_admit(p->lex);
    if(r<=0) {
        if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"Absolute import code inputs changed");
        return -1;
    }
    module=PyImport_ImportModuleLevelObject(p->lex->import_name,p->lex->import_globals,
        p->lex->import_globals,Py_None,0);
    if(!module)return -1;
    Py_DECREF(module);p->absolute_imports++;return 0;
}
static int role_tick(LexPlan *p,int op) {
    if(p->calls[op]>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Role lexical counter bound");return -1;}
    p->calls[op]++;return 0;
}
static PyObject *role_lexical_path(DescriptorPlan *ctx,PyObject *path,PyObject *path_type) {
    PyObject *value;
    if(path_type!=ctx->lex->cls||!Py_IS_TYPE(path,(PyTypeObject *)path_type))Py_RETURN_NOTIMPLEMENTED;
    value=lex_string(ctx->lex,path);
    if(value&&value!=Py_NotImplemented&&!PyUnicode_CheckExact(value))Py_SETREF(value,Py_NewRef(Py_NotImplemented));
    if(value&&value!=Py_NotImplemented&&role_tick(ctx->lex,2)<0)Py_CLEAR(value);
    return value;
}
static PyObject *role_parts(DescriptorPlan *ctx,PyObject *path) {
    LexPlan *p=ctx->lex;PyObject *drv=NULL,*root=NULL,*tail=NULL,*result=NULL,*loaded;Py_ssize_t length=0;int missing;
    if(!Py_IS_TYPE(path,(PyTypeObject *)p->cls))Py_RETURN_NOTIMPLEMENTED;
    drv=lex_attr(p,path,1);if(PyErr_Occurred())goto done;
    root=lex_attr(p,path,2);if(PyErr_Occurred())goto done;
    tail=lex_attr(p,path,3);if(PyErr_Occurred())goto done;
    missing=(!drv)+(!root)+(!tail);
    if(missing==3) {
        loaded=lex_load(p,path);if(!loaded)goto done;
        if(loaded==Py_NotImplemented){result=loaded;goto done;}
        Py_DECREF(loaded);if(role_tick(p,1)<0)goto done;
        drv=lex_attr(p,path,1);root=lex_attr(p,path,2);tail=lex_attr(p,path,3);
        if(!drv||!root||!tail){if(PyErr_Occurred())goto done;goto unsupported;}
    } else if(missing)goto unsupported;
    if(!PyUnicode_CheckExact(drv)||PyUnicode_GET_LENGTH(drv)||!PyUnicode_CheckExact(root)||
        !lex_strings(tail,&length))goto unsupported;
    result=PyTuple_Pack(3,drv,root,tail);goto done;
unsupported:result=Py_NewRef(Py_NotImplemented);
done:Py_XDECREF(drv);Py_XDECREF(root);Py_XDECREF(tail);return result;
}
static PyObject *role_construct(DescriptorPlan *ctx,PyObject *args,int derived) {
    LexPlan *p=ctx->lex;PyObject *raw=NULL,*value=NULL,*imported=NULL;Py_ssize_t i,length=0;int r;
    /* Decline foreign inputs before allocation/import callbacks. The original
     * constructor allocates its object, imports (on Ubuntu), then copies raw
     * arguments. Never retain a pre-import copy of a mutable argument list. */
    if(PyTuple_GET_SIZE(args)>64)Py_RETURN_NOTIMPLEMENTED;
    for(i=0;i<PyTuple_GET_SIZE(args);i++) {
        PyObject *arg=PyTuple_GET_ITEM(args,i);
        if(PyUnicode_CheckExact(arg)) {
            if(PyUnicode_GET_LENGTH(arg)>8192)Py_RETURN_NOTIMPLEMENTED;
        } else if(Py_IS_TYPE(arg,(PyTypeObject *)p->cls)) {
            PyObject *input=lex_attr(p,arg,0);int valid;
            if(!input){if(PyErr_Occurred())return NULL;Py_RETURN_NOTIMPLEMENTED;}
            valid=lex_strings(input,&length);Py_DECREF(input);if(!valid)Py_RETURN_NOTIMPLEMENTED;
        } else Py_RETURN_NOTIMPLEMENTED;
    }
    value=PyType_GenericAlloc((PyTypeObject *)p->cls,0);if(!value)return NULL;
    if(p->import_globals) {
        r=lex_import_admit(p);if(r<=0)goto changed;
        imported=PyImport_ImportModuleLevelObject(p->import_name,p->import_globals,p->import_globals,Py_None,0);
        if(!imported)goto error;
    }
    raw=lex_raw(p,args);if(!raw)goto error;
    if(raw==Py_NotImplemented)goto changed;
    if(PyObject_GenericSetAttr(value,p->names[0],raw)<0)goto error;
    Py_XDECREF(imported);Py_DECREF(raw);
    if(value&&(role_tick(p,0)<0||(derived&&role_tick(p,3)<0)))Py_CLEAR(value);
    return value;
changed:if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"Role constructor inputs changed after allocation");
error:Py_XDECREF(raw);Py_XDECREF(imported);Py_DECREF(value);return NULL;
}
static PyObject *role_from_parts(DescriptorPlan *ctx,PyObject *parts,Py_ssize_t n) {
    LexPlan *p=ctx->lex;PyObject *tail=NULL,*joined=NULL,*text=NULL,*args=NULL,*value=NULL;
    tail=PyList_GetSlice(PyTuple_GET_ITEM(parts,2),0,n);if(!tail)goto done;
    joined=PyUnicode_Join(p->slash,tail);if(!joined)goto done;
    text=PyUnicode_Concat(PyTuple_GET_ITEM(parts,1),joined);if(!text)goto done;
    args=PyTuple_Pack(1,text);if(!args)goto done;
    value=role_construct(ctx,args,1);if(!value||value==Py_NotImplemented)goto done;
    if(PyObject_GenericSetAttr(value,p->names[4],PyUnicode_GET_LENGTH(text)?text:p->dot)<0||
        PyObject_GenericSetAttr(value,p->names[1],PyTuple_GET_ITEM(parts,0))<0||
        PyObject_GenericSetAttr(value,p->names[2],PyTuple_GET_ITEM(parts,1))<0||
        PyObject_GenericSetAttr(value,p->names[3],tail)<0)Py_CLEAR(value);
done:Py_XDECREF(tail);Py_XDECREF(joined);Py_XDECREF(text);Py_XDECREF(args);return value;
}
static PyObject *role_parent(DescriptorPlan *ctx,PyObject *path) {
    PyObject *parts=role_parts(ctx,path),*value;Py_ssize_t n;
    if(!parts||parts==Py_NotImplemented)return parts;
    n=PyList_GET_SIZE(PyTuple_GET_ITEM(parts,2));
    value=n?role_from_parts(ctx,parts,n-1):Py_NewRef(path);Py_DECREF(parts);return value;
}
static PyObject *role_name(DescriptorPlan *ctx,PyObject *path) {
    PyObject *parts=role_parts(ctx,path),*tail,*value;Py_ssize_t n;
    if(!parts||parts==Py_NotImplemented)return parts;
    tail=PyTuple_GET_ITEM(parts,2);n=PyList_GET_SIZE(tail);
    value=Py_NewRef(n?PyList_GET_ITEM(tail,n-1):ctx->lex->empty);Py_DECREF(parts);return value;
}
static PyObject *role_parents(DescriptorPlan *ctx,PyObject *path) {
    PyObject *parts=role_parts(ctx,path),*tail,*list=NULL,*parent=NULL,*name=NULL,*result=NULL;Py_ssize_t i;
    if(!parts||parts==Py_NotImplemented)return parts;
    tail=PyTuple_GET_ITEM(parts,2);list=PyList_New(0);if(!list)goto done;
    for(i=0;i<PyList_GET_SIZE(tail);i++) {
        parent=role_from_parts(ctx,parts,PyList_GET_SIZE(tail)-i-1);if(!parent)goto done;
        if(parent==Py_NotImplemented){result=Py_NewRef(Py_NotImplemented);goto done;}
        name=role_lexical_path(ctx,parent,ctx->lex->cls);if(!name)goto done;
        if(name==Py_NotImplemented){result=Py_NewRef(Py_NotImplemented);goto done;}
        if(PyList_Append(list,name)<0)goto done;
        Py_CLEAR(parent);Py_CLEAR(name);
    }
    result=PyList_AsTuple(list);
done:Py_DECREF(parts);Py_XDECREF(list);Py_XDECREF(parent);Py_XDECREF(name);return result;
}

static PyObject *role_path_rows(DescriptorPlan *ctx,PyObject *source,PyObject *path_type,const char *spec,Py_ssize_t limit,int names) {
    PyObject *result,*v,*name,*copy,*set,*tuple;Py_ssize_t i,j,n=(Py_ssize_t)strlen(spec);int r;
    if(!PyTuple_CheckExact(source)||PyTuple_GET_SIZE(source)>limit)return Py_NewRef(Py_NotImplemented);
    result=PyTuple_New(PyTuple_GET_SIZE(source));if(!result)return NULL;
    for(i=0;i<PyTuple_GET_SIZE(source);i++) {
        v=PyTuple_GET_ITEM(source,i);
        if(!PyTuple_CheckExact(v)||PyTuple_GET_SIZE(v)!=n)goto unsupported;
        name=role_lexical_path(ctx,PyTuple_GET_ITEM(v,0),path_type);
        if(!name)goto error;
        if(name==Py_NotImplemented){Py_DECREF(name);goto unsupported;}
        copy=PyTuple_New(n);if(!copy){Py_DECREF(name);goto error;}
        PyTuple_SET_ITEM(copy,0,name);
        for(j=1;j<n;j++)PyTuple_SET_ITEM(copy,j,Py_NewRef(PyTuple_GET_ITEM(v,j)));
        if(names) {
            set=PyTuple_GET_ITEM(v,1);
            if(!PyFrozenSet_CheckExact(set)||PySet_GET_SIZE(set)>1024){Py_DECREF(copy);goto unsupported;}
            tuple=PySequence_Tuple(set);if(!tuple){Py_DECREF(copy);goto error;}
            Py_DECREF(PyTuple_GET_ITEM(copy,1));PyTuple_SET_ITEM(copy,1,tuple);
            for(j=0;j<PyTuple_GET_SIZE(tuple);j++)if(!PyUnicode_CheckExact(PyTuple_GET_ITEM(tuple,j))) {
                Py_DECREF(copy);goto unsupported;
            }
        }
        r=row(copy,spec);if(r<=0){Py_DECREF(copy);if(r<0)goto error;goto unsupported;}
        PyTuple_SET_ITEM(result,i,copy);
    }
    return result;
unsupported:Py_DECREF(result);return Py_NewRef(Py_NotImplemented);
error:Py_DECREF(result);return NULL;
}
static PyObject *role_prepare_plan(DescriptorPlan *ctx,PyObject *subject,PyObject *owner,PyObject *path_type) {
    const char *fields[]={"uid","entries","directories","machine","files","parents",NULL};
    PyObject *dict=plain_fields(subject,owner,fields),*entries=NULL,*dirs=NULL,*machine=NULL,*files=NULL,*parents=NULL,*result=NULL;
    unsigned long long uid;int r;
    if(!dict||dict==Py_NotImplemented)return dict;
    r=u64(PyDict_GetItemString(dict,"uid"),&uid);if(r<=0)goto unsupported;
    entries=role_path_rows(ctx,PyDict_GetItemString(dict,"entries"),path_type,"st",16,1);
    if(!entries)goto done;
    if(entries==Py_NotImplemented)goto unsupported;
    dirs=role_path_rows(ctx,PyDict_GetItemString(dict,"directories"),path_type,"ssuuu",64,0);
    if(!dirs)goto done;
    if(dirs==Py_NotImplemented)goto unsupported;
    machine=role_lexical_path(ctx,PyDict_GetItemString(dict,"machine"),path_type);
    if(!machine)goto done;
    if(machine==Py_NotImplemented)goto unsupported;
    files=role_path_rows(ctx,PyDict_GetItemString(dict,"files"),path_type,"ssubnuu",64,0);
    if(!files)goto done;
    if(files==Py_NotImplemented)goto unsupported;
    parents=role_path_rows(ctx,PyDict_GetItemString(dict,"parents"),path_type,"ssbb",256,0);
    if(!parents)goto done;
    if(parents==Py_NotImplemented)goto unsupported;
    result=PyTuple_Pack(6,PyDict_GetItemString(dict,"uid"),entries,dirs,machine,files,parents);goto done;
unsupported:if(!PyErr_Occurred())result=Py_NewRef(Py_NotImplemented);
done:Py_DECREF(dict);Py_XDECREF(entries);Py_XDECREF(dirs);Py_XDECREF(machine);Py_XDECREF(files);Py_XDECREF(parents);return result;
}
static PyObject *role_parent_descriptor(DescriptorPlan *ctx,PyObject *directories,PyObject *path) {
    PyObject *parent=role_parent(ctx,path),*item;
    if(!parent||parent==Py_NotImplemented)return parent;
    item=PyDict_GetItemWithError(directories,parent);Py_DECREF(parent);
    if(!item){if(PyErr_Occurred())return NULL;return Py_NewRef(Py_NotImplemented);}
    if(!PyTuple_CheckExact(item)||PyTuple_GET_SIZE(item)!=2)return Py_NewRef(Py_NotImplemented);
    return Py_NewRef(PyTuple_GET_ITEM(item,0));
}
static PyObject *role_prepare_custody(DescriptorPlan *ctx,PyObject *subject,PyObject *owner,PyObject *path_type) {
    const char *fields[]={"uid","gid","root","directory","lock_path","directories","known","retained","entries","directory_metadata","lock",NULL};
    PyObject *dict=plain_fields(subject,owner,fields),*directories,*known,*retained,*entries,*metadata;
    PyObject *rows_o=NULL,*leaves=NULL,*lock=NULL,*path,*item,*original,*extra,*names;
    PyObject *name=NULL,*parent=NULL,*temp=NULL,*result=NULL,*v;Py_ssize_t pos=0,i=0;unsigned long long uid,gid;int r,equal;
    if(!dict||dict==Py_NotImplemented)return dict;
    r=u64(PyDict_GetItemString(dict,"uid"),&uid);if(r<=0)goto unsupported;
    r=u64(PyDict_GetItemString(dict,"gid"),&gid);if(r<=0)goto unsupported;
    for(i=2;i<5;i++) {
        temp=role_lexical_path(ctx,PyDict_GetItemString(dict,fields[i]),path_type);
        if(!temp)goto done;
        if(temp==Py_NotImplemented)goto unsupported;
        Py_CLEAR(temp);
    }
    directories=PyDict_GetItemString(dict,"directories");known=PyDict_GetItemString(dict,"known");
    retained=PyDict_GetItemString(dict,"retained");entries=PyDict_GetItemString(dict,"entries");metadata=PyDict_GetItemString(dict,"directory_metadata");
    if(!PyDict_CheckExact(directories)||PyDict_GET_SIZE(directories)>256 || !PyDict_CheckExact(known)||PyDict_GET_SIZE(known)>1024 ||
       !PyDict_CheckExact(retained)||!PyDict_CheckExact(metadata)||(entries!=Py_None&&!PyDict_CheckExact(entries)))goto unsupported;
    rows_o=PyTuple_New(PyDict_GET_SIZE(directories));leaves=PyTuple_New(PyDict_GET_SIZE(known));if(!rows_o||!leaves)goto done;
    i=0;
    while(PyDict_Next(directories,&pos,&path,&item)) {
        if(!Py_IS_TYPE(path,(PyTypeObject *)path_type)||!PyTuple_CheckExact(item)||PyTuple_GET_SIZE(item)!=2)goto unsupported;
        r=descriptor(PyTuple_GET_ITEM(item,0));if(r<=0)goto unsupported;
        original=PyTuple_GET_ITEM(item,1);r=row(original,"uuuuunn");if(r<=0)goto unsupported;
        equal=PyObject_RichCompareBool(path,PyDict_GetItemString(dict,"directory"),Py_EQ);if(equal<0)goto done;
        if(equal){parent=Py_NewRef(Py_None);name=role_lexical_path(ctx,path,path_type);}
        else {
            parent=role_parent_descriptor(ctx,directories,path);if(!parent)goto done;
            if(parent==Py_NotImplemented)goto unsupported;
            r=descriptor(parent);if(r<=0)goto unsupported;
            name=role_name(ctx,path);
        }
        if(!name)goto done;
        if(name==Py_NotImplemented)goto unsupported;
        extra=entries==Py_None?Py_None:PyDict_GetItemWithError(metadata,path);
        names=entries==Py_None?Py_None:PyDict_GetItemWithError(entries,path);
        if(!extra||!names){if(PyErr_Occurred())goto done;goto unsupported;}
        if(entries!=Py_None){r=row(extra,"uuuuuunnn");if(r<=0)goto unsupported;if(!strings(names,0))goto unsupported;}
        v=PyTuple_Pack(6,name,parent,PyTuple_GET_ITEM(item,0),original,extra,names);if(!v)goto done;
        r=row(v,"szutOL");if(r<=0){Py_DECREF(v);goto unsupported;}
        PyTuple_SET_ITEM(rows_o,i++,v);Py_CLEAR(parent);Py_CLEAR(name);
    }
    pos=0;i=0;
    while(PyDict_Next(known,&pos,&path,&original)) {
        if(!Py_IS_TYPE(path,(PyTypeObject *)path_type))goto unsupported;
        r=row(original,"uuuuuunnn");if(r<=0)goto unsupported;
        parent=role_parent_descriptor(ctx,directories,path);if(!parent)goto done;
        if(parent==Py_NotImplemented)goto unsupported;
        r=descriptor(parent);if(r<=0)goto unsupported;
        item=PyDict_GetItemWithError(retained,path);if(!item&&PyErr_Occurred())goto done;
        if(item){r=descriptor(item);if(r<=0)goto unsupported;}else item=Py_None;
        name=role_name(ctx,path);if(!name)goto done;
        v=PyTuple_Pack(4,name,parent,original,item);if(!v)goto done;
        r=row(v,"sutz");if(r<=0){Py_DECREF(v);goto unsupported;}
        PyTuple_SET_ITEM(leaves,i++,v);Py_CLEAR(parent);Py_CLEAR(name);
    }
    item=PyDict_GetItemString(dict,"lock");
    if(item==Py_None)lock=Py_NewRef(Py_None);
    else {
        r=descriptor(item);if(r<=0)goto unsupported;
        original=PyDict_GetItemWithError(known,PyDict_GetItemString(dict,"lock_path"));
        if(!original){if(PyErr_Occurred())goto done;goto unsupported;}
        r=row(original,"uuuuuunnn");if(r<=0)goto unsupported;
        lock=PyTuple_Pack(2,item,original);if(!lock)goto done;
    }
    result=PyTuple_Pack(5,PyDict_GetItemString(dict,"uid"),PyDict_GetItemString(dict,"gid"),rows_o,leaves,lock);goto done;
unsupported:if(!PyErr_Occurred())result=Py_NewRef(Py_NotImplemented);
done:Py_DECREF(dict);Py_XDECREF(rows_o);Py_XDECREF(leaves);Py_XDECREF(lock);Py_XDECREF(name);Py_XDECREF(parent);Py_XDECREF(temp);return result;
}


static PyObject *role_finish(DescriptorPlan *p,PyObject *result,int observed) {
    PyObject *pending=PyErr_GetRaisedException();int r=desc_admit(p->lex,0);
    if(r<=0||(observed&&result==Py_NotImplemented)) {
        p->lex->broken=1;PyDict_Clear(p->lex->cache);
    }
    if(pending){PyErr_Clear();PyErr_SetRaisedException(pending);Py_XDECREF(result);return NULL;}
    if(!result&&!PyErr_Occurred()) {
        PyErr_SetString(PyExc_SystemError,"Role failed without an exception");return NULL;
    }
    if(r<=0||(observed&&result==Py_NotImplemented)) {
        Py_XDECREF(result);
        if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"Role changed or unsupported after observations");
        return NULL;
    }
    return result;
}
static PyObject *role_prepare(PyObject *unused,PyObject *args) {
    PyObject *capsule,*kind_o,*payload,*owner,*result=NULL,*path=NULL,*parts=NULL,*name=NULL,*parents=NULL;
    PyObject *argtuple=NULL,*raw,*maximum=NULL,*uid=NULL,*executable=Py_False,*resolved=NULL,*tail;
    DescriptorPlan *p;unsigned long long kind,n;long long limit;Py_ssize_t i;int r,observed=0;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOO",&capsule,&kind_o,&payload,&owner))return NULL;
    p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);if(!p)return NULL;
    r=u64(kind_o,&kind);if(r<=0||kind>7)goto invalid;
    if(!p->role_configured)Py_RETURN_NOTIMPLEMENTED;
    r=desc_admit(p->lex,0);if(r<0)return NULL;if(!r)Py_RETURN_NOTIMPLEMENTED;
    if(p->role_prepares[kind]>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Role preparation bound");return NULL;}
    if(kind==2){result=role_prepare_plan(p,payload,owner,p->lex->cls);goto done;}
    if(kind==3){result=role_prepare_custody(p,payload,owner,p->lex->cls);goto done;}
    if(owner!=Py_None||!PyTuple_CheckExact(payload))goto unsupported;
    if(kind<2) {
        if(PyTuple_GET_SIZE(payload)!=(kind==0?3:1))goto unsupported;
        raw=PyTuple_GET_ITEM(payload,0);
        if(kind==0) {
            maximum=PyTuple_GET_ITEM(payload,1);executable=PyTuple_GET_ITEM(payload,2);
            r=i64(maximum,&limit);if(r<=0)goto unsupported;
            if(limit<=0||!PyBool_Check(executable))goto unsupported;
        } else {
            maximum=PyLong_FromLong(268435456);if(!maximum)goto done;executable=Py_True;
        }
    } else if(kind<6) {
        if(PyTuple_GET_SIZE(payload)!=4)goto unsupported;
        raw=PyTuple_GET_ITEM(payload,0);uid=PyTuple_GET_ITEM(payload,1);
        maximum=PyTuple_GET_ITEM(payload,2);executable=PyTuple_GET_ITEM(payload,3);
        r=u64(uid,&n);if(r<=0)goto unsupported;
        r=i64(maximum,&limit);if(r<=0)goto unsupported;
        if(limit<=0||limit>16777216||!PyBool_Check(executable)||
            (kind==4&&n!=0)||(kind==5&&executable!=Py_False))goto unsupported;
    } else {
        if(PyTuple_GET_SIZE(payload)!=2)goto unsupported;
        raw=PyTuple_GET_ITEM(payload,0);maximum=PyTuple_GET_ITEM(payload,1);
        r=i64(maximum,&limit);if(r<=0)goto unsupported;
        if(limit<0||limit>16777216)goto unsupported;
        if(PyUnicode_CheckExact(raw))name=Py_NewRef(raw);
        else name=role_lexical_path(p,raw,p->lex->cls);
        if(!name)goto done;
        if(name==Py_NotImplemented)goto unsupported;
        if(PyUnicode_GET_LENGTH(name)>8192)goto unsupported;
        parents=PyTuple_New(0);uid=PyLong_FromLong(0);if(!parents||!uid)goto done;
        result=PyTuple_Pack(5,name,parents,uid,maximum,Py_False);goto done;
    }
    argtuple=PyTuple_Pack(1,raw);if(!argtuple)goto done;
    path=role_construct(p,argtuple,0);if(!path)goto done;if(path==Py_NotImplemented)goto unsupported;
    if(kind==1) {
        /* resolve remains the original SDK filesystem operation. Once called,
         * no unsupported result may trigger a second resolving walk. */
        r=desc_admit(p->lex,0);if(r<0)goto done;if(!r)goto unsupported;
        observed=1;resolved=PyObject_CallMethod(path,"resolve","O",Py_True);if(!resolved)goto done;
        Py_SETREF(path,resolved);resolved=NULL;
        if(!Py_IS_TYPE(path,(PyTypeObject *)p->lex->cls))goto unsupported;
    }
    /* Ubuntu's is_absolute has its own original local import, after the
     * constructor and before anchor/parts. resolve above executes its own
     * original SDK path; it does not add this emulated absolute test. */
    if(kind!=1&&role_absolute_import(p)<0)goto done;
    parts=role_parts(p,path);if(!parts)goto done;if(parts==Py_NotImplemented)goto unsupported;
    tail=PyTuple_GET_ITEM(parts,2);
    if(PyList_GET_SIZE(tail)+1>64)goto unsupported;
    if(PyUnicode_Compare(PyTuple_GET_ITEM(parts,1),p->lex->slash))goto unsupported;
    for(i=0;i<PyList_GET_SIZE(tail);i++)if(!PyUnicode_CompareWithASCIIString(PyList_GET_ITEM(tail,i),".."))goto unsupported;
    name=role_lexical_path(p,path,p->lex->cls);if(!name)goto done;if(name==Py_NotImplemented)goto unsupported;
    if(!PyUnicode_CheckExact(name)||PyUnicode_GET_LENGTH(name)>8192)goto unsupported;
    parents=role_parents(p,path);if(!parents)goto done;if(parents==Py_NotImplemented)goto unsupported;
    if(kind<2)result=PyTuple_Pack(4,name,parents,maximum,executable);
    else result=PyTuple_Pack(5,name,parents,uid,maximum,executable);
    goto done;
unsupported:if(!PyErr_Occurred())result=Py_NewRef(Py_NotImplemented);
done:
    if(result&&result!=Py_NotImplemented)p->role_prepares[kind]++;
    Py_XDECREF(path);Py_XDECREF(parts);Py_XDECREF(name);Py_XDECREF(parents);Py_XDECREF(argtuple);Py_XDECREF(resolved);
    if(kind==1)Py_XDECREF(maximum);
    if(kind>=6)Py_XDECREF(uid);
    return role_finish(p,result,observed);
invalid:if(!PyErr_Occurred())PyErr_SetString(PyExc_TypeError,"Invalid observation role preparation");return NULL;
}
static PyObject *role_admit(PyObject *unused,PyObject *capsule) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);int r;(void)unused;
    if(!p)return NULL;
    if(!p->role_configured)Py_RETURN_FALSE;
    r=desc_admit(p->lex,0);if(r<0)return NULL;return PyBool_FromLong(r);
}
static PyObject *role_observe(PyObject *unused,PyObject *args) {
    PyObject *capsule,*kind_o,*prepared,*callbacks,*call=NULL,*result=NULL,*number=NULL;
    DescriptorPlan *p;unsigned long long kind,before_f,before_p,before_c,before_r;Py_ssize_t i,n;int r,observed;(void)unused;
    if(!PyArg_ParseTuple(args,"OOOO",&capsule,&kind_o,&prepared,&callbacks))return NULL;
    p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);if(!p)return NULL;
    r=u64(kind_o,&kind);if(r<=0||kind>7||!PyTuple_CheckExact(prepared)||!PyTuple_CheckExact(callbacks)||PyTuple_GET_SIZE(callbacks)!=4)goto invalid;
    if(!p->role_configured)Py_RETURN_NOTIMPLEMENTED;
    r=desc_admit(p->lex,0);if(r<0)return NULL;if(!r)Py_RETURN_NOTIMPLEMENTED;
    if(p->role_calls[kind]>=LEX_LIMIT){PyErr_SetString(PyExc_ValueError,"Role observation bound");return NULL;}
    n=PyTuple_GET_SIZE(prepared);
    if((kind<2&&n!=4)||(kind==2&&n!=6)||(kind>=3&&n!=5))goto invalid;
    before_f=fingerprint_calls;before_p=plan_calls;before_c=custody_calls;before_r=read_calls;
    if(kind<2)result=fingerprint(NULL,prepared);
    else if(kind==2||kind==3) {
        call=PyTuple_New(n+1);if(!call)goto done;
        for(i=0;i<n;i++)PyTuple_SET_ITEM(call,i,Py_NewRef(PyTuple_GET_ITEM(prepared,i)));
        PyTuple_SET_ITEM(call,n,Py_NewRef(PyTuple_GET_ITEM(callbacks,kind==2?0:1)));
        result=kind==2?persistent(NULL,call):custody(NULL,call);
    } else {
        number=PyLong_FromUnsignedLongLong(kind-4);if(!number)goto done;
        call=PyTuple_Pack(8,number,PyTuple_GET_ITEM(prepared,0),PyTuple_GET_ITEM(prepared,1),
            PyTuple_GET_ITEM(prepared,2),PyTuple_GET_ITEM(prepared,3),PyTuple_GET_ITEM(prepared,4),
            PyTuple_GET_ITEM(callbacks,2),PyTuple_GET_ITEM(callbacks,3));if(!call)goto done;
        result=read_file(NULL,call);
    }
done:
    Py_XDECREF(call);Py_XDECREF(number);
    observed=before_f!=fingerprint_calls||before_p!=plan_calls||before_c!=custody_calls||before_r!=read_calls;
    if(observed)p->role_calls[kind]++;
    return role_finish(p,result,observed);
invalid:if(!PyErr_Occurred())PyErr_SetString(PyExc_TypeError,"Invalid observation role");return NULL;
}
static PyObject *role_counts(PyObject *unused,PyObject *capsule) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);PyObject *prepares,*observations,*result;Py_ssize_t i;(void)unused;
    if(!p)return NULL;
    if(!desc_owner(p)||!p->role_configured){PyErr_SetString(PyExc_ValueError,"Role owner or configuration changed");return NULL;}
    prepares=PyTuple_New(8);observations=PyTuple_New(8);
    if(!prepares||!observations){Py_XDECREF(prepares);Py_XDECREF(observations);return NULL;}
    for(i=0;i<8;i++) {
        PyObject *a=PyLong_FromUnsignedLongLong(p->role_prepares[i]),*b=PyLong_FromUnsignedLongLong(p->role_calls[i]);
        if(!a||!b){Py_XDECREF(a);Py_XDECREF(b);Py_DECREF(prepares);Py_DECREF(observations);return NULL;}
        PyTuple_SET_ITEM(prepares,i,a);PyTuple_SET_ITEM(observations,i,b);
    }
    result=PyTuple_Pack(2,prepares,observations);Py_DECREF(prepares);Py_DECREF(observations);return result;
}
static PyObject *role_imports(PyObject *unused,PyObject *capsule) {
    DescriptorPlan *p=PyCapsule_GetPointer(capsule,DESC_CAPSULE);(void)unused;
    if(!p)return NULL;
    if(!desc_owner(p)||!p->role_configured){PyErr_SetString(PyExc_ValueError,"Role owner or configuration changed");return NULL;}
    return Py_BuildValue("(OK)",p->absolute_import?Py_True:Py_False,p->absolute_imports);
}

static PyMethodDef methods[]={
    {"role_configure",role_configure,METH_VARARGS,"Bind the authenticated complete-role import mode once."},
    {"role_imports",role_imports,METH_O,"Bounded original absolute-test import witnesses."},
    {"role_prepare",role_prepare,METH_VARARGS,"Complete lexical argument preparation inside fresh role admission."},
    {"role_observe",role_observe,METH_VARARGS,"Original ordered observations inside fresh role admission."},
    {"role_admit",role_admit,METH_O,"Fresh owner/code input check for one complete role."},
    {"role_counts",role_counts,METH_O,"Bounded preparation and observation role witnesses."},
    {"descriptor_plan",descriptor_plan,METH_VARARGS,"Prepare a main-interpreter lexical method context."},
    {"descriptor_entries",descriptor_entries,METH_O,"Create four capsule-bound SDK instance methods once."},
    {"descriptor_bind",descriptor_bind,METH_VARARGS,"Bind finite live code inputs once; no observations."},
    {"descriptor_phase",descriptor_phase,METH_VARARGS,"Fresh admission and dictionary notification lifecycle."},
    {"descriptor_counts",descriptor_counts,METH_O,"Closed bounded native entry/fallback/cache counters."},
    {"descriptor_close",descriptor_close,METH_O,"Release code inputs and cache; saved methods fall back."},
    {"path_plan",lex_plan_new,METH_VARARGS,"Prepare immutable lexical code/schema context; no filesystem results."},
    {"path_call",lex_path_call,METH_VARARGS,"Original-class lexical SDK operations with fresh live admission."},
    {"prepare_tables",prepare_tables,METH_VARARGS,"Finite ephemeral lexical argument preparation; no observations."},
    {"read_file",read_file,METH_VARARGS,"Fresh complete Root/private/raw reads; no retained observations."},
    {"read_counts",read_counts,METH_NOARGS,"Bounded complete-read diagnostic counts."},
    {"fingerprint",fingerprint,METH_VARARGS,"Fresh ordered Root file metadata."},
    {"persistent",persistent,METH_VARARGS,"Fresh fixed persistent metadata; no retained observations."},
    {"custody",custody,METH_VARARGS,"Fresh held and named Root custody metadata."},
    {"same_bindings",same_bindings,METH_VARARGS,"Original Root owner and live metadata hook admission."},
    {"counts",counts,METH_NOARGS,"Bounded diagnostic call counts."},{NULL,NULL,0,NULL}
};
static struct PyModuleDef definition={PyModuleDef_HEAD_INIT,"_native_metadata_probe",NULL,-1,methods,NULL,NULL,NULL,NULL};
PyMODINIT_FUNC PyInit__native_metadata_probe(void){return PyModule_Create(&definition);}
