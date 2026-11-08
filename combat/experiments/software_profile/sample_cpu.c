#define _GNU_SOURCE
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <unistd.h>
#include <dirent.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>
typedef struct {int fd,tid;unsigned char *map;uint64_t tail;} Event;
typedef struct {int tid;uint64_t ip;unsigned count;} Bucket;
static Bucket buckets[16384];static unsigned used;
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void copy_ring(unsigned char *ring,size_t size,uint64_t position,void *out,size_t count){size_t offset=position%size,first=size-offset;if(first>count)first=count;memcpy(out,ring+offset,first);if(first<count)memcpy((unsigned char *)out+first,ring,count-first);}
static void drain(Event *event,size_t page){
    struct perf_event_mmap_page *meta=(void *)event->map;uint64_t head=meta->data_head;size_t size=page*8;__sync_synchronize();
    while(event->tail<head){struct perf_event_header header;uint64_t ip;unsigned i;copy_ring(event->map+page,size,event->tail,&header,sizeof(header));if(header.size<sizeof(header)||header.size>size)break;
        if(header.type==PERF_RECORD_SAMPLE){copy_ring(event->map+page,size,event->tail+sizeof(header),&ip,sizeof(ip));for(i=0;i<used;i++)if(buckets[i].tid==event->tid&&buckets[i].ip==ip)break;if(i==used&&used<16384){buckets[used].tid=event->tid;buckets[used].ip=ip;used++;}if(i<16384)buckets[i].count++;}
        event->tail+=header.size;
    }
    __sync_synchronize();meta->data_tail=event->tail;
}
int main(int argc,char **argv){
    char path[128];DIR *directory;struct dirent *entry;Event events[64];unsigned count=0,i;size_t page=(size_t)sysconf(_SC_PAGESIZE);double end;struct timespec nap={0,10000000};
    if(argc!=2)return 2;snprintf(path,sizeof(path),"/proc/%d/task",atoi(argv[1]));directory=opendir(path);if(!directory)return 2;
    while((entry=readdir(directory))&&count<64){struct perf_event_attr attr;int tid=atoi(entry->d_name),fd;void *map;if(!tid)continue;memset(&attr,0,sizeof(attr));attr.size=sizeof(attr);attr.type=PERF_TYPE_SOFTWARE;attr.config=PERF_COUNT_SW_CPU_CLOCK;attr.sample_period=1000000;attr.sample_type=PERF_SAMPLE_IP;attr.exclude_kernel=1;attr.exclude_hv=1;fd=syscall(__NR_perf_event_open,&attr,tid,-1,-1,0);if(fd<0){fprintf(stderr,"perf_event_open tid=%d: %s\n",tid,strerror(errno));continue;}map=mmap(NULL,page*9,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(map==MAP_FAILED){close(fd);continue;}events[count].fd=fd;events[count].tid=tid;events[count].map=map;events[count].tail=0;count++;}
    closedir(directory);if(!count)return 3;end=now()+3;
    while(now()<end){for(i=0;i<count;i++)drain(events+i,page);nanosleep(&nap,NULL);}
    for(i=0;i<count;i++){drain(events+i,page);munmap(events[i].map,page*9);close(events[i].fd);}
    puts("tid,ip,samples");for(i=0;i<used;i++)printf("%d,0x%llx,%u\n",buckets[i].tid,(unsigned long long)buckets[i].ip,buckets[i].count);return 0;
}
