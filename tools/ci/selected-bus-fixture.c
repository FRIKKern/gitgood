/* Deterministic test-owned sd-bus ABI. No IPC, systemd or host resources. */
#define _GNU_SOURCE 1
#include <stdint.h>
#include <string.h>
#include <signal.h>
#include <time.h>

typedef struct message {
    char name[257];int append,depth,read,array_index,request;
} sd_bus_message;
typedef struct sd_bus_error sd_bus_error;
typedef struct slot sd_bus_slot;
typedef int (*handler)(sd_bus_message *,void *,sd_bus_error *);
typedef struct bus { int marker; } sd_bus;
struct slot { int serial;handler callback;void *userdata;sd_bus_message reply; };
static sd_bus bus;
static sd_bus_slot slots[32],*current;
static sd_bus_message requests[32];
static int mode,queued,next_reply,processes,waits,request_unrefs,reply_unrefs,closed,wire_ok,cancel_count,cancel_at_close;
static int cancels[32];
static char text[2050];

void fixture_reset(int selected)
{
    memset(slots,0,sizeof(slots));memset(requests,0,sizeof(requests));memset(cancels,0,sizeof(cancels));
    mode=selected;queued=0;next_reply=-1;processes=0;waits=0;request_unrefs=0;reply_unrefs=0;
    closed=0;wire_ok=1;cancel_count=0;cancel_at_close=-1;current=NULL;memset(text,'x',sizeof(text));text[2049]=0;
}
void *fixture_bus(void) { return &bus; }
int fixture_stat(int field)
{
    switch (field) {
    case 0:return queued;case 1:return processes;case 2:return waits;case 3:return request_unrefs;
    case 4:return reply_unrefs;case 5:return closed;case 6:return wire_ok;case 7:return cancel_count;
    case 40:return cancel_at_close;
    default:return field>=8 && field<40 ? cancels[field-8] : -1;
    }
}
int sd_bus_message_new_method_call(sd_bus *original,sd_bus_message **message,const char *destination,
                                  const char *path,const char *interface,const char *member)
{
    if (original!=&bus || queued>=32) return -22;
    wire_ok &= !strcmp(destination,"org.freedesktop.systemd1") && path[0]=='/'
        && !strcmp(interface,"org.freedesktop.DBus.Properties") && !strcmp(member,"Get");
    *message=&requests[queued];(*message)->request=1;
    if (mode==20 && queued==1) return -5; /* Allocated request on refusal. */
    return 0;
}
int sd_bus_message_append_basic(sd_bus_message *message,char type,const void *value)
{
    if (type!='s' || value==NULL) return -22;
    if (mode==21 && queued==1) return -5;
    if (message->append++==1) {
        if (strnlen(value,257)>256) return -22;
        strcpy(message->name,value);
    }
    return 0;
}
int sd_bus_call_async(sd_bus *original,sd_bus_slot **target,sd_bus_message *message,
                      handler callback,void *userdata,uint64_t timeout)
{
    sd_bus_slot *slot;
    if (original!=&bus || queued>=32 || message->append!=2) return -22;
    wire_ok &= timeout==UINT64_C(5000000) && (uintptr_t)userdata==(uintptr_t)(queued+1);
    slot=&slots[queued];slot->serial=queued+1;slot->callback=callback;slot->userdata=userdata;
    strcpy(slot->reply.name,message->name);*target=slot;queued++;next_reply=queued-1;
    if (mode==13 && queued==2) return -5; /* Slot returned even with queue error. */
    if (mode==22) { *target=NULL;return 0; }
    return 0;
}
int sd_bus_process(sd_bus *original,sd_bus_message **message)
{
    sd_bus_slot *slot;
    (void)message;
    if (original!=&bus) return -22;
    processes++;
    if (mode==14) return -5;
    if (mode==15 || mode==17) return 0;
    if (mode==16) return 1;
    if (mode==18) { raise(SIGINT);return 1; }
    if (next_reply<0) return 0;
    slot=&slots[next_reply--];current=mode==3 ? &slots[(slot->serial)%32] : slot;
    slot->callback(&slot->reply,mode==2 ? (void *)(uintptr_t)999 : slot->userdata,NULL);
    if (mode==1) slot->callback(&slot->reply,slot->userdata,NULL);
    if (mode==23) slot->callback(&slot->reply,NULL,NULL);
    current=NULL;return 1;
}
int sd_bus_wait(sd_bus *original,uint64_t timeout)
{
    struct timespec pause;
    if (original!=&bus || !timeout || timeout>UINT64_C(5000000)) return -22;
    waits++;
    if (mode==15) return -5;
    if (mode==17) {
        pause.tv_sec=(time_t)(timeout/UINT64_C(1000000));
        pause.tv_nsec=(long)(timeout%UINT64_C(1000000))*1000;
        nanosleep(&pause,NULL);
    }
    return 0;
}
sd_bus_slot *sd_bus_get_current_slot(sd_bus *original) { return original==&bus ? current : NULL; }
sd_bus_slot *sd_bus_slot_unref(sd_bus_slot *slot)
{
    if (cancel_count<32) cancels[cancel_count++]=slot->serial;
    return NULL;
}
int sd_bus_message_is_method_error(sd_bus_message *message,const char *name)
{ (void)message;(void)name;return mode==4 ? 1 : 0; }
int sd_bus_message_has_signature(sd_bus_message *message,const char *signature)
{ (void)message;return mode==5 ? 0 : !strcmp(signature,"v"); }
int sd_bus_message_enter_container(sd_bus_message *message,char type,const char *signature)
{
    const char *expected=!strcmp(message->name,"U") ? "u" : !strcmp(message->name,"B") ? "b"
        : !strcmp(message->name,"A") ? "as" : "s";
    if (mode==6) return -22;
    if (type=='v' && message->depth==0 && !strcmp(signature,expected)) { message->depth=1;return 1; }
    if (type=='a' && message->depth==1 && !strcmp(signature,"s") && !strcmp(expected,"as")) {
        message->depth=2;return 1;
    }
    return -22;
}
int sd_bus_message_read_basic(sd_bus_message *message,char type,void *value)
{
    if (mode==24) return 0;
    if (type=='s') {
        const char *result="live";
        if (mode==10) result="\377";
        if (mode==11) result=text;
        if (mode==25) result=NULL;
        if (mode==26) { text[2048]=0;result=text; }
        *(const char **)value=result;
        if (message->depth==2) message->array_index++;
    } else if (type=='u') *(uint32_t *)value=UINT32_MAX;
    else if (type=='b') *(int *)value=mode==9 ? 2 : mode==27 ? 0 : 1;
    else return -22;
    message->read=1;return 1;
}
int sd_bus_message_exit_container(sd_bus_message *message)
{
    if (mode==28) return -22;
    if (message->depth<1) return -22;
    if (message->depth==2) message->read=1;
    message->depth--;return 0;
}
int sd_bus_message_at_end(sd_bus_message *message,int complete)
{
    (void)complete;
    if (mode==29) return -22;
    if (message->depth==2) return message->array_index>=(mode==12 ? 33 : mode==30 ? 32 : mode==31 ? 0 : 2);
    if (mode==7 && message->depth==1) return 0;
    if (mode==8 && message->depth==0) return 0;
    return message->read;
}
sd_bus_message *sd_bus_message_unref(sd_bus_message *message)
{
    if (message->request) request_unrefs++;else reply_unrefs++;
    return NULL;
}
sd_bus *sd_bus_flush_close_unref(sd_bus *original)
{ if (original==&bus) { closed++;cancel_at_close=cancel_count; }return NULL; }
