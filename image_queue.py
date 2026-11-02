"""Small worker pool whose pending jobs follow the current viewport."""
from concurrent.futures import Future
import threading


class ImageQueue:
    def __init__(self,workers=4):
        self.condition=threading.Condition();self.jobs=[];self.closed=False
        self.threads=[threading.Thread(target=self.run,daemon=True,name=f'galeria-image-{i}') for i in range(workers)]
        for thread in self.threads:thread.start()

    def submit(self,work,priority=10):
        future=Future()
        with self.condition:
            if self.closed:raise RuntimeError('Image queue is closed')
            self.jobs.append((future,work,priority));self.condition.notify()
        return future

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.jobs)
                if not self.jobs:return
                ranked=[(job[2]() if callable(job[2]) else job[2],job) for job in self.jobs]
                stale=[job for priority,job in ranked if priority is None]
                ranked=[entry for entry in ranked if entry[0] is not None]
                self.jobs=[job for _,job in ranked]
                next_job=self.jobs.pop(min(range(len(ranked)),key=lambda i:ranked[i][0])) if ranked else None
            # Reap abandoned view jobs together, instead of rescanning the queue
            # once per stale future while GTK competes with the workers for Python.
            for future,_,_ in stale:
                if future.set_running_or_notify_cancel():future.set_result(None)
            if next_job is None:continue
            future,work,_=next_job
            if not future.set_running_or_notify_cancel():continue
            try:future.set_result(work())
            except BaseException as error:future.set_exception(error)

    def shutdown(self,wait=True,cancel_futures=False):
        with self.condition:
            self.closed=True
            pending=self.jobs if cancel_futures else [];self.jobs=[] if cancel_futures else self.jobs
            self.condition.notify_all()
        for future,_,_ in pending:future.cancel()
        if wait:
            for thread in self.threads:thread.join()
