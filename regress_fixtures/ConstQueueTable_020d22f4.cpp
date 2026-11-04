#include <globaldefs.h>
#include <NitroSDK/Interrupts.h>

struct SoundCommand020d22f4 {
    SoundCommand020d22f4* next;
};

struct SoundCommandState020d22f4 {
    SoundCommand020d22f4* freeList;
    unsigned long finishedTag;
    unsigned char pad8[8];
    SoundCommand020d22f4* freeListEnd;
    int waitingQueueRead;
    unsigned char pad18[4];
    int waitingCount;
};

extern SoundCommandState020d22f4 data_02112780;
extern SoundCommand020d22f4* data_021127a4[9];

unsigned long ReadUncachedField0();
extern "C" void func_020c976c(unsigned long cycles);

// USA: func_020d22f4
extern "C" ARM void* func_020d22f4(unsigned long flags) {
    int lastState = DisableIRQInterrupts();
    SoundCommand020d22f4* list;
    SoundCommand020d22f4* end;
    if (flags & 1) {
        if (data_02112780.finishedTag == ReadUncachedField0()) {
            do {
                SetIRQInterruptState(lastState);
                func_020c976c(100);
                lastState = DisableIRQInterrupts();
            } while (data_02112780.finishedTag == ReadUncachedField0());
        }
    } else if (data_02112780.finishedTag == ReadUncachedField0()) {
        SetIRQInterruptState(lastState);
        return NULL;
    }
    list = data_021127a4[data_02112780.waitingQueueRead];
    if (++data_02112780.waitingQueueRead > 8)
        data_02112780.waitingQueueRead = 0;
    end = list;
    if (end->next != NULL) {
        do {
            end = end->next;
        } while (end->next != NULL);
    }
    if (data_02112780.freeListEnd != NULL)
        data_02112780.freeListEnd->next = list;
    else
        data_02112780.freeList = list;
    data_02112780.freeListEnd = end;
    data_02112780.waitingCount--;
    data_02112780.finishedTag++;
    SetIRQInterruptState(lastState);
    return list;
}
