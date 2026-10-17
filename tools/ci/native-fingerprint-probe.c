/* Diagnostic prototype only. No production use or acceptance.
 * Match native_service_scope._CapturedRootFiles._fingerprint's ordered lstat
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

static PyMethodDef methods[] = {
    {"fingerprint", fingerprint, METH_VARARGS, "Fresh bounded diagnostic fingerprint; no authority or effects."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef definition = {
    PyModuleDef_HEAD_INIT, "_fingerprint_probe", NULL, -1, methods,
    NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC PyInit__fingerprint_probe(void)
{
    return PyModule_Create(&definition);
}
