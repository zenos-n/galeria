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
                index=min(range(len(self.jobs)),key=lambda i:self.jobs[i][2]() if callable(self.jobs[i][2]) else self.jobs[i][2])
                future,work,_=self.jobs.pop(index)
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
