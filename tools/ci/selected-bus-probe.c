/* Hosted-only diagnostic. No production import or adoption.
 * Selected Get protocol engine, matching systemd v255 sd-bus.h and the
 * existing native_systemd_properties.ReadOnlySystemdProperties._read_selected.
 * No connection is created or owned here. Keep the GIL: callbacks are invoked
 * synchronously by the original bus on the original Python/Root thread.
 */
#define _GNU_SOURCE 1
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <dlfcn.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef struct sd_bus sd_bus;
typedef struct sd_bus_message sd_bus_message;
typedef struct sd_bus_slot sd_bus_slot;
typedef struct sd_bus_error sd_bus_error;
typedef int (*message_handler)(sd_bus_message *, void *, sd_bus_error *);

struct api {
    int (*sd_bus_message_new_method_call)(sd_bus *,sd_bus_message **,const char *,const char *,const char *,const char *);
    int (*sd_bus_message_append_basic)(sd_bus_message *,char,const void *);
    int (*sd_bus_call_async)(sd_bus *,sd_bus_slot **,sd_bus_message *,message_handler,void *,uint64_t);
    int (*sd_bus_process)(sd_bus *,sd_bus_message **);
    int (*sd_bus_wait)(sd_bus *,uint64_t);
    sd_bus_slot *(*sd_bus_get_current_slot)(sd_bus *);
    sd_bus_slot *(*sd_bus_slot_unref)(sd_bus_slot *);
    int (*sd_bus_message_is_method_error)(sd_bus_message *,const char *);
    int (*sd_bus_message_has_signature)(sd_bus_message *,const char *);
    int (*sd_bus_message_read_basic)(sd_bus_message *,char,void *);
    int (*sd_bus_message_enter_container)(sd_bus_message *,char,const char *);
    int (*sd_bus_message_exit_container)(sd_bus_message *);
    int (*sd_bus_message_at_end)(sd_bus_message *,int);
    sd_bus_message *(*sd_bus_message_unref)(sd_bus_message *);
};

struct binding {
    struct api functions;
    sd_bus *bus;
    PyObject *owner; /* Strong lifetime reference; the original Python owner. */
    PyObject *library,*bus_object;
    void *handle;
    pid_t pid;
    unsigned long thread;
    int (*owner_valid)(struct binding *); /* Fresh original owner/bus/handle check. */
};

struct property {
    const char *interface;
    const char *name;
    const char *signature;
    PyObject *key; /* Borrowed from entry's retained exact property tuple. */
};

struct context {
    struct binding *binding;
    const struct property *properties;
    size_t count,queued;
    sd_bus_slot *slots[32];
    PyObject *result;
    uint64_t deadline;
    int failed;
};

static _Thread_local struct context *active;

static int owner_valid(struct binding *binding)
{
    PyObject *usable=NULL,*library=NULL,*bus=NULL,*handle=NULL,*pointer=NULL;
    int valid=0;
    if (getuid()!=0 || geteuid()!=0 || getgid()!=0 || getegid()!=0) return 0;
    usable=PyObject_GetAttrString(binding->owner,"usable");
    library=PyObject_GetAttrString(binding->owner,"library");
    bus=PyObject_GetAttrString(binding->owner,"bus");
    if (usable!=Py_True || library!=binding->library || bus!=binding->bus_object) goto done;
    handle=PyObject_GetAttrString(library,"_handle");
    pointer=PyObject_GetAttrString(bus,"value");
    if (handle==NULL || pointer==NULL || !PyLong_CheckExact(handle) || !PyLong_CheckExact(pointer)) goto done;
    valid=PyLong_AsVoidPtr(handle)==binding->handle && PyLong_AsVoidPtr(pointer)==(void *)binding->bus;
done:
    Py_XDECREF(usable);Py_XDECREF(library);Py_XDECREF(bus);Py_XDECREF(handle);Py_XDECREF(pointer);
    return valid && !PyErr_Occurred();
}

static int monotonic_ns(uint64_t *value)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now)<0 || now.tv_sec<0 || now.tv_nsec<0) return 0;
    *value=(uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec;
    return 1;
}

static int current_owner(struct binding *binding)
{
    return binding->pid==getpid() && binding->thread==PyThread_get_thread_ident()
        && binding->owner_valid(binding);
}

static PyObject *read_string(struct api *api,sd_bus_message *message)
{
    const char *text=NULL;
    size_t length;
    if (api->sd_bus_message_read_basic(message,'s',&text)!=1 || text==NULL) return NULL;
    length=strnlen(text,2049);
    if (length>2048) return NULL;
    return PyUnicode_DecodeASCII(text,(Py_ssize_t)length,"strict");
}

static PyObject *read_value(struct api *api,sd_bus_message *message,const char *signature)
{
    PyObject *value=NULL,*items=NULL,*separator=NULL;
    uint32_t number=0;
    int boolean=0;
    if (!strcmp(signature,"s")) value=read_string(api,message);
    else if (!strcmp(signature,"u")) {
        if (api->sd_bus_message_read_basic(message,'u',&number)!=1) return NULL;
        value=PyUnicode_FromFormat("%u",(unsigned int)number);
    } else if (!strcmp(signature,"b")) {
        if (api->sd_bus_message_read_basic(message,'b',&boolean)!=1 || (boolean!=0 && boolean!=1)) return NULL;
        value=PyUnicode_FromString(boolean ? "yes" : "no");
    } else if (!strcmp(signature,"as")) {
        if (api->sd_bus_message_enter_container(message,'a',"s")!=1) return NULL;
        items=PyList_New(0);
        if (items==NULL) return NULL;
        while (api->sd_bus_message_at_end(message,0)==0) {
            PyObject *item;
            if (PyList_GET_SIZE(items)>=32) goto done;
            item=read_string(api,message);
            if (item==NULL) goto done;
            if (PyList_Append(items,item)<0) { Py_DECREF(item);goto done; }
            Py_DECREF(item);
        }
        if (api->sd_bus_message_exit_container(message)<0) goto done;
        separator=PyUnicode_FromString(" ");
        if (separator!=NULL) value=PyUnicode_Join(separator,items);
    } else return NULL;
    if (value!=NULL && api->sd_bus_message_at_end(message,0)!=1) Py_CLEAR(value);
done:
    Py_XDECREF(separator);Py_XDECREF(items);
    return value;
}

static int completed(sd_bus_message *message,void *userdata,sd_bus_error *error)
{
    struct context *context=active;
    uintptr_t serial=(uintptr_t)userdata;
    size_t index;
    struct api *api;
    PyObject *value=NULL;
    (void)error;
    if (context==NULL) return 1;
    api=&context->binding->functions;
    if (context->failed || !current_owner(context->binding) || serial<1 || serial>context->queued) goto failed;
    if (message==NULL) goto failed;
    index=(size_t)serial-1;
    if (context->slots[index]==NULL || api->sd_bus_get_current_slot(context->binding->bus)!=context->slots[index]) goto failed;
    if (PyDict_Contains(context->result,context->properties[index].key)!=0) goto failed;
    if (api->sd_bus_message_is_method_error(message,NULL)!=0 || api->sd_bus_message_has_signature(message,"v")!=1) goto failed;
    if (api->sd_bus_message_enter_container(message,'v',context->properties[index].signature)!=1) goto failed;
    value=read_value(api,message,context->properties[index].signature);
    if (value==NULL || api->sd_bus_message_exit_container(message)<0 || api->sd_bus_message_at_end(message,0)!=1) goto failed;
    if (PyDict_SetItem(context->result,context->properties[index].key,value)<0) goto failed;
    Py_DECREF(value);return 1;
failed:
    Py_XDECREF(value);PyErr_Clear();context->failed=1;
    /* As in the Python callback, no exception escapes into sd-bus. */
    return 1;
}

/* Caller must validate/retain exact path/property strings and bind only the
 * existing owner/library/bus. NULL is an internal error; Py_None is refusal.
 * The original Python _get_many must bracket this with library observations
 * and perform its existing permanent close on refusal or any exception.
 */
static PyObject *selected_get(struct binding *binding,const char *path,
                              const struct property *properties,size_t count)
{
    struct context context={0};
    struct api *api=&binding->functions;
    PyObject *answer=NULL;
    uint64_t now;
    unsigned int processed=0;
    size_t index;
    if (active!=NULL || count<1 || count>32 || !current_owner(binding) || !monotonic_ns(&now)) {
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }
    context.binding=binding;context.properties=properties;context.count=count;
    context.deadline=now+UINT64_C(5000000000);context.result=PyDict_New();
    if (context.result==NULL) return NULL;
    active=&context;
    for (index=0;index<count;index++) {
        sd_bus_message *message=NULL;
        if (PyErr_CheckSignals()<0) goto cleanup;
        if (!current_owner(binding) || !monotonic_ns(&now) || now>=context.deadline) goto cleanup;
        context.queued=index+1;
        if (api->sd_bus_message_new_method_call(binding->bus,&message,"org.freedesktop.systemd1",path,
                "org.freedesktop.DBus.Properties","Get")<0) goto message_done;
        if (api->sd_bus_message_append_basic(message,'s',properties[index].interface)<0
                || api->sd_bus_message_append_basic(message,'s',properties[index].name)<0) goto message_done;
        if (api->sd_bus_call_async(binding->bus,&context.slots[index],message,completed,(void *)(uintptr_t)(index+1),
                UINT64_C(5000000))<0 || context.slots[index]==NULL) goto message_done;
        api->sd_bus_message_unref(message);continue;
message_done:
        if (message!=NULL) api->sd_bus_message_unref(message);
        goto cleanup;
    }
    while ((size_t)PyDict_Size(context.result)<count) {
        int status;
        if (PyErr_CheckSignals()<0) goto cleanup;
        if (context.failed || !current_owner(binding) || !monotonic_ns(&now) || now>=context.deadline) goto cleanup;
        if (++processed>4096) goto cleanup;
        status=api->sd_bus_process(binding->bus,NULL);
        if (status<0) goto cleanup;
        if (status==0) {
            uint64_t remaining;
            if (!monotonic_ns(&now) || now>=context.deadline) goto cleanup;
            remaining=(context.deadline-now)/UINT64_C(1000);
            if (api->sd_bus_wait(binding->bus,remaining ? remaining : 1)<0) goto cleanup;
        }
    }
    if (!context.failed && (size_t)PyDict_Size(context.result)==count && current_owner(binding)) {
        /* Keep callback-visible result alive until every slot is cancelled. */
        answer=Py_NewRef(context.result);
    }
cleanup:
    /* Cancel every original pending slot before releasing callback context. */
    for (index=context.queued;index>0;index--)
        if (context.slots[index-1]!=NULL) api->sd_bus_slot_unref(context.slots[index-1]);
    active=NULL;
    Py_XDECREF(context.result);
    if (answer!=NULL && (context.failed || !current_owner(binding))) Py_CLEAR(answer);
    if (PyErr_Occurred()) { Py_XDECREF(answer);return NULL; }
    if (answer!=NULL) return answer;
    Py_RETURN_NONE;
}

#define CAPSULE_NAME "gitgood.diagnostic.selected_bus.v1"

static void destroy_binding(PyObject *capsule)
{
    struct binding *binding=PyCapsule_GetPointer(capsule,CAPSULE_NAME);
    if (binding==NULL) { PyErr_Clear();return; }
    Py_DECREF(binding->owner);Py_DECREF(binding->library);Py_DECREF(binding->bus_object);
    PyMem_Free(binding); /* Original bus and CDLL remain owned by Python. */
}

static PyObject *bind_owner(PyObject *self,PyObject *owner)
{
    struct binding *binding=NULL;
    PyObject *handle=NULL,*pointer=NULL,*capsule=NULL;
    (void)self;
    if (getuid()!=0 || geteuid()!=0 || getgid()!=0 || getegid()!=0) Py_RETURN_NONE;
    binding=PyMem_Calloc(1,sizeof(*binding));
    if (binding==NULL) return PyErr_NoMemory();
    binding->owner=Py_NewRef(owner);
    binding->library=PyObject_GetAttrString(owner,"library");
    binding->bus_object=PyObject_GetAttrString(owner,"bus");
    if (binding->library==NULL || binding->bus_object==NULL) goto done;
    handle=PyObject_GetAttrString(binding->library,"_handle");
    pointer=PyObject_GetAttrString(binding->bus_object,"value");
    if (handle==NULL || pointer==NULL || !PyLong_CheckExact(handle) || !PyLong_CheckExact(pointer)) goto done;
    binding->handle=PyLong_AsVoidPtr(handle);binding->bus=PyLong_AsVoidPtr(pointer);
    if (PyErr_Occurred() || binding->handle==NULL || binding->bus==NULL) goto done;
    binding->pid=getpid();binding->thread=PyThread_get_thread_ident();binding->owner_valid=owner_valid;
    if (!current_owner(binding)) goto done;
#define RESOLVE(name) do { \
    void *address=dlsym(binding->handle,#name); \
    _Static_assert(sizeof(address)==sizeof(binding->functions.name),"function pointer ABI"); \
    if (address==NULL) goto done; \
    memcpy(&binding->functions.name,&address,sizeof(address)); \
} while (0)
    RESOLVE(sd_bus_message_new_method_call);RESOLVE(sd_bus_message_append_basic);
    RESOLVE(sd_bus_call_async);RESOLVE(sd_bus_process);RESOLVE(sd_bus_wait);
    RESOLVE(sd_bus_get_current_slot);RESOLVE(sd_bus_slot_unref);
    RESOLVE(sd_bus_message_is_method_error);RESOLVE(sd_bus_message_has_signature);
    RESOLVE(sd_bus_message_read_basic);RESOLVE(sd_bus_message_enter_container);
    RESOLVE(sd_bus_message_exit_container);RESOLVE(sd_bus_message_at_end);RESOLVE(sd_bus_message_unref);
#undef RESOLVE
    capsule=PyCapsule_New(binding,CAPSULE_NAME,destroy_binding);
    if (capsule!=NULL) binding=NULL;
done:
    Py_XDECREF(handle);Py_XDECREF(pointer);
    if (binding!=NULL) {
        Py_XDECREF(binding->owner);Py_XDECREF(binding->library);Py_XDECREF(binding->bus_object);PyMem_Free(binding);
    }
    if (capsule!=NULL) return capsule;
    if (PyErr_Occurred()) return NULL;
    Py_RETURN_NONE;
}

static const char *bounded_string(PyObject *value,Py_ssize_t maximum,int empty)
{
    const char *text;
    Py_ssize_t length;
    if (!PyUnicode_CheckExact(value) || PyUnicode_GET_LENGTH(value)>maximum) return NULL;
    text=PyUnicode_AsUTF8AndSize(value,&length);
    if (text==NULL || (!empty && length==0) || memchr(text,0,(size_t)length)!=NULL) return NULL;
    return text;
}

static PyObject *read_selected(PyObject *self,PyObject *args)
{
    PyObject *capsule,*path_object,*items;
    struct binding *binding;
    struct property properties[32];
    const char *path;
    Py_ssize_t count,index,prior;
    (void)self;
    if (!PyArg_ParseTuple(args,"OOO",&capsule,&path_object,&items)) return NULL;
    binding=PyCapsule_GetPointer(capsule,CAPSULE_NAME);
    if (binding==NULL) return NULL;
    path=bounded_string(path_object,1024,0);
    if (path==NULL || path[0]!='/' || !PyTuple_CheckExact(items)) goto refused;
    count=PyTuple_GET_SIZE(items);
    if (count<1 || count>32) goto refused;
    for (index=0;index<count;index++) {
        PyObject *item=PyTuple_GET_ITEM(items,index),*key;
        if (!PyTuple_CheckExact(item) || PyTuple_GET_SIZE(item)!=3) goto refused;
        properties[index].interface=bounded_string(PyTuple_GET_ITEM(item,0),256,0);
        key=PyTuple_GET_ITEM(item,1);properties[index].key=key;
        properties[index].name=bounded_string(key,256,0);
        properties[index].signature=bounded_string(PyTuple_GET_ITEM(item,2),2,0);
        if (properties[index].interface==NULL || properties[index].name==NULL || properties[index].signature==NULL) goto refused;
        if (strcmp(properties[index].signature,"s") && strcmp(properties[index].signature,"u")
                && strcmp(properties[index].signature,"b") && strcmp(properties[index].signature,"as")) goto refused;
        for (prior=0;prior<index;prior++)
            if (!strcmp(properties[index].name,properties[prior].name)) goto refused;
    }
    /* args retains all borrowed strings until reverse cancellation completes. */
    return selected_get(binding,path,properties,(size_t)count);
refused:
    if (PyErr_Occurred()) return NULL;
    Py_RETURN_NONE;
}

static PyMethodDef methods[]={
    {"bind_owner",bind_owner,METH_O,"Bind the original Root-owned bus without reconnecting."},
    {"read_selected",read_selected,METH_VARARGS,"Read one fresh selected batch on the bound bus."},
    {NULL,NULL,0,NULL}
};
static struct PyModuleDef module={
    PyModuleDef_HEAD_INIT,.m_name="_selected_bus_probe",.m_doc="Hosted-only selected Get diagnostic.",
    .m_size=-1,.m_methods=methods
};
PyMODINIT_FUNC PyInit__selected_bus_probe(void) { return PyModule_Create(&module); }
