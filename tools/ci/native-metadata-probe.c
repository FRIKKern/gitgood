/* Diagnostic prototype only. No production use or acceptance.
 * Four finite original metadata families: Root files, executables, persistent
 * paths and held history custody. Preserve ordered fresh lstat/fstat operations,
 * predicates and tuple fields. No observation survives a call.
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
        } else current=PyObject_GetItem(owner,PyTuple_GET_ITEM(v,1));
        if(!current){if(PyErr_ExceptionMatches(PyExc_KeyError)){PyErr_Clear();Py_RETURN_FALSE;}return NULL;}
        r=current==PyTuple_GET_ITEM(v,2);Py_DECREF(current);if(!r)Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
unsupported:if(PyErr_Occurred())return NULL;PyErr_SetString(PyExc_TypeError,"Invalid metadata hook bindings");return NULL;
}
static PyObject *counts(PyObject *unused,PyObject *args) {
    (void)unused;(void)args;
    return Py_BuildValue("{sK,sK,sK}","fingerprint",fingerprint_calls,"persistent",plan_calls,"custody",custody_calls);
}
static PyMethodDef methods[]={
    {"fingerprint",fingerprint,METH_VARARGS,"Fresh ordered Root file metadata."},
    {"persistent",persistent,METH_VARARGS,"Fresh fixed persistent metadata; no retained observations."},
    {"custody",custody,METH_VARARGS,"Fresh held and named Root custody metadata."},
    {"same_bindings",same_bindings,METH_VARARGS,"Original Root owner and live metadata hook admission."},
    {"counts",counts,METH_NOARGS,"Bounded diagnostic call counts."},{NULL,NULL,0,NULL}
};
static struct PyModuleDef definition={PyModuleDef_HEAD_INIT,"_native_metadata_probe",NULL,-1,methods,NULL,NULL,NULL,NULL};
PyMODINIT_FUNC PyInit__native_metadata_probe(void){return PyModule_Create(&definition);}
