# Lesson 60 — Case Study: Online Judge with Sandboxed Code Execution (LeetCode)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — "run strangers' code safely and fairly" is a favourite twist on a queue-and-workers design, and most answers say "put it in a Docker container" and stop.
>
> **Study time:** 80 minutes. **Do this after:** Distributed Message Queue (SQS / RabbitMQ); Distributed Task Scheduler; Docker & Container Internals; Overload, Load Shedding and Cascading Failures; Real-Time Gaming Leaderboard at 10M QPS.
>
> **Level:** extended.

An online judge takes source code from people you do not trust, runs it on your machines against hidden tests, and returns a verdict a contestant will dispute at the second decimal of a running time. The sandbox is only one of four hard parts: the others are a verdict that is defensible (what counts as the right output, which limit fired first), a time measurement that is stable on shared hardware, and a queue that stays fair when ten thousand people submit in the last ten minutes. The code here is checked in `test/lesson_code/sy60_check.py`; capacity numbers come from `capacity_check_f.py`. Queues, workers and leases are not re-taught (see Distributed Message Queue (SQS / RabbitMQ) and Distributed Task Scheduler), nor the container basics (see Docker & Container Internals); rankings are the subject of Real-Time Gaming Leaderboard at 10M QPS.

**What was and was not read.** The sandbox facts come from the manuals and papers listed in Sources: the `isolate` manual (a sandbox its own text says is meant for programming contests), the gVisor documentation, the Firecracker paper and the Linux manual pages for seccomp, namespaces and cgroups. **No engineering post, paper or documentation from LeetCode, Codeforces or any other judge operator was read**, so nothing below says how any of them is built; the design is the general approach, and every figure marked *assumed* is this lesson's own.

---

## 1. Mental Model

> **A judge sells a verdict, not a sandbox. Isolation protects your machines from the program; limits protect your queue from the program; the checker protects the contestant from your bugs; and a measurement protocol protects the ranking from noise. A submission is correct only if all four agree.**

- **Untrusted does not mean malicious.** Most programs that misbehave are merely wrong: infinite loops, a million-element recursion, 4 GB of output. Limits catch these every day; isolation catches the rare hostile one.
- **Every limit has a verdict name and a precedence.** "Time limit" is at least two clocks (CPU and wall). A run that breaks two limits must always get the same verdict.
- **Timing is a measurement.** The same program on a shared machine measures differently from run to run, so a protocol (dedicated core, re-measure near the limit) is part of the design.
- **Fairness is queue design.** Under a burst, first come first served lets one user's flood delay everyone, and no amount of isolation fixes that.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "run user-submitted code" | a sandbox built from kernel isolation (namespaces, cgroups, a syscall filter) or a stronger boundary (an application kernel or a micro-VM), plus per-run limits; say which threat each layer answers (section 5) |
| "just use Docker" | a container is namespaces and cgroups; name what it does not stop (a kernel bug) and what you add |
| "time limit exceeded", "why is my time different today" | CPU time as the main limit, wall time as a backstop, a dedicated core, re-measure near the limit (section 7) |
| "a contest with 10,000 users" | an autoscaled worker fleet sized for the peak, and per-user fair queueing (sections 3 and 8) |
| "tests must not leak" | hidden tests never enter the sandbox's file system; the program gets stdin, the checker runs outside |
| "the answer is a floating-point number" or "any valid answer is accepted" | a checker mode or a special checker, never exact text (section 6) |

---

## 3. Requirements and Capacity

**Functional.** Submit source in a language; compile; run against ordered hidden tests; return a verdict (accepted, wrong answer, time limit, memory limit, output limit, runtime error, compile error) with the first failing test; show the run time and memory; rejudge on demand; a contest scoreboard. **Out of scope:** the editor, discussions, plagiarism detection, the scoreboard algorithm.

**Non-functional.** Never let a program touch the host, other submissions or the hidden tests; a verdict within seconds in practice and within a bounded time in a contest; the same submission gets the same verdict (up to a stated timing tolerance); no submission lost when a worker dies.

**Capacity estimate** (a contest; every input *assumed*, results reproduced by `capacity_check_f.py`):

| Input | Value |
|---|---|
| contest | 10,000 participants, 2 hours, 6 submissions each on average |
| shape | a quarter of all submissions arrive in the last 10 minutes |
| cost of one submission | 2.0 core-seconds to compile; 30 tests at 0.15 core-seconds each |
| outcome mix | 40% run all 30 tests; 60% stop early, at an average of 6 tests |
| fleet | one sandbox per core, aimed at 60% utilisation |

| Result | Arithmetic | Value |
|---|---|---|
| submissions | 10,000 x 6 | 60,000 |
| average and peak rate | 60,000 / 7,200 s; 60,000 x 25% / 600 s | 8.3 per second; 25 per second |
| tests actually run | 0.4 x 30 + 0.6 x 6 | 15.6 per submission |
| cost of one submission | 2.0 + 15.6 x 0.15 | 4.34 core-seconds |
| cores busy | at the peak, 25 x 4.34 | 108.5 |
| workers for the peak | 108.5 / 0.6 | 181 |
| workers for the average | 8.33 x 4.34 / 0.6 | 61 |
| a fleet of 60 at the peak | backlog grows by (25 - 60 / 4.34) per second for 600 s | 6,705 queued; the last one waits 485 seconds |

Three conclusions. **Compile time is nearly half the cost** (2.0 of 4.34 core-seconds), so compile once per submission, not per test, and cache by (language, source hash). **Early exit is the biggest lever:** stopping at the first failing test is why 15.6 tests run, not 30. **A fleet sized for the average loses the contest at the end:** 61 workers sound plenty, yet the last-ten-minutes backlog means an eight-minute verdict. Size for the peak or scale on queue age; sections 8 and 10 show what to do when you cannot.

---

## 4. API and Data Model

```
POST /submissions       {problem, language, source, idempotency_key}  ->  {id}      # key makes a double click one submission
GET  /submissions/{id}  ->  {state: queued|compiling|running|done, verdict, tests: [{n, verdict, cpu_ms, kb}], first_failure}
```

- `submissions(id, user, problem, language, source_ref, state, verdict, created_at)`; source goes to object storage, the row holds a reference.
- `problems(id, tests_ref, cpu_limit, mem_limit, output_limit, checker)`. Tests live in object storage and are cached on workers by content hash; **the verdict page may show the first failing test's number, not its data** unless the problem allows it.
- `results(submission, test, verdict, cpu_ms, peak_kb)`, written as tests finish so the page can stream progress.
- **State only moves forward** (queued, compiling, running, done). A worker takes a submission with a lease; if the worker dies the lease expires and another takes it, so the result writer must be idempotent per (submission, test). This is the visibility-timeout pattern of the queue lessons.

---

## 5. What a Sandbox Is Made Of

Start from threats, then name the mechanism. This is the part interviewers push on.

| Threat | Mechanism | What it does not stop |
|---|---|---|
| reads or writes files it should not | a private mount namespace with a minimal, mostly read-only file system; hidden tests never mounted | a kernel bug that escapes the namespace |
| talks to the network | a new network namespace with no device but loopback (the `isolate` manual: "creates a new network namespace for its child process") | nothing, if you leave it out: a judge that allows sockets can be a proxy |
| fork bomb | a process limit: `isolate` allows one process by default; cgroup v2 `pids.max` makes `fork()` fail with EAGAIN | a program allowed many threads for a language runtime that needs them |
| eats memory | an address-space limit (`isolate --mem`: allocations fail) or a cgroup memory limit (`memory.max`: the out-of-memory killer runs inside the group) | memory that is not counted (see the pitfalls) |
| eats CPU forever | CPU-time limit, plus a wall-clock limit for sleepers | time spent waiting on a lock another process holds |
| floods output or fills the disk | a file-size limit (`--fsize`) or a quota, and a cap in the runner | a quota that is not enabled on the file system |
| calls a dangerous system call | a seccomp-BPF filter (the manual: `SECCOMP_SET_MODE_FILTER` needs `no_new_privs` or `CAP_SYS_ADMIN`; the filter is inherited by children and kept across `execve`) | **kernel bugs in the calls you allow**; a filter only narrows the interface |
| exploits the kernel | a smaller or separate kernel: gVisor or a micro-VM | hardware side channels |

**Where each stronger boundary sits** (all from the documents in Sources):

- **`isolate`**: the namespaces, control groups and limits above in one setuid tool, with a documented sequence `--init`, `--run`, `--cleanup` and a meta file reporting `time`, `time-wall`, `max-rss`, `status` (`RE`, `SG`, `TO`, `XX`) and `cg-oom-killed`. Its manual recommends **not** running it inside containers (control groups are not delegated properly, and "you do not want to share the machine with other workloads, which would influence measurement of execution time") and turning swap off, because memory limits do not apply to swapped-out data.
- **gVisor**: "an application kernel" that implements a Linux-like interface in a memory-safe language in user space, so the program's system calls hit the Sentry instead of the host kernel. Its documentation says it is not a syscall filter and not a VM. Its costs are structural for system-call-heavy programs and, per its performance guide, there is no extra cost for plain CPU work, which is what most judged programs do.
- **A micro-VM** (Firecracker): a hardware-virtualised guest. The paper reports under 5 MB of memory overhead per micro-VM, boot to application code in under 125 ms, and up to 150 micro-VMs created per second per host. That startup is wasted on a 0.15 s test but acceptable once per submission, so the unit is a sandbox per submission (compile and all tests), cleaned between submissions, never per test.

**A sandbox is not a secure architecture.** The gVisor security guide says it plainly: "A sandbox is not a substitute for a secure architecture". The judge's own services (the checker, the tests store, the queue) must be unreachable from the sandbox, and workers hold no credentials a program could use.

**What to say in the interview.** Name the layers: no network, no tests visible, small process and memory limits, a syscall filter, a separate user, throw-away file system, and then say the one residual risk (a kernel escape) and the two ways to shrink it (an application kernel, or a micro-VM), with the cost of each.

---

## 6. Judging One Run

### 6.1 The checker

The expected output rarely matches byte for byte. Common modes are exact, line-wise ignoring trailing spaces and blank lines, token-wise ignoring all whitespace, and floating point with a tolerance. Problems with many valid answers need a special checker program that reads the input, the contestant's output and the jury's answer; it runs outside the contestant's sandbox, with its own limits.

```python
import re

_NUM = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def compare(expected: str, actual: str, mode: str = "tokens", eps: float = 1e-6) -> bool:
    """exact: byte for byte. lines: ignore trailing spaces and trailing blank lines. tokens: same whitespace-separated
    tokens. float: tokens, numbers within eps absolute or relative (relative to the expected value)."""
    if mode == "exact":
        return expected == actual
    if mode == "lines":
        norm = lambda s: [ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")]
        a, b = norm(expected), norm(actual)
        while a and a[-1] == "":
            a.pop()
        while b and b[-1] == "":
            b.pop()
        return a == b
    a, b = expected.split(), actual.split()
    if len(a) != len(b):                      # zip would silently ignore extra tokens
        return False
    if mode == "tokens":
        return a == b
    for x, y in zip(a, b):
        if x == y:
            continue
        if not (_NUM.match(x) and _NUM.match(y)):   # float() accepts "nan", "inf" and "1_0"; a judge must not
            return False
        if abs(float(x) - float(y)) > eps * max(1.0, abs(float(x))):
            return False
    return True
```

The comments are the bugs: comparing with `zip` accepts extra output; `float("1_0")` is 10.0 in Python, so a contestant printing `1_0` would pass a tolerance check; `nan` compares unequal to everything and `inf` makes the tolerance infinite. The check compares this against an independent formulation (absolute-or-relative) on 4,000 random token strings, including both sides of the tolerance boundary.

### 6.2 The verdict

Each limit has a name; the order in which you test them decides what a contestant sees when a run breaks two, so fix it and test it.

```python
from dataclasses import dataclass


@dataclass
class Limits:
    cpu_s: float
    mem_kb: int
    out_bytes: int


@dataclass
class Run:
    exit_code: int = 0
    signal: int = 0          # fatal signal, 0 if none
    cpu_s: float = 0.0
    peak_kb: int = 0
    out_bytes: int = 0
    killed: str = ""         # "", "cpu", "wall", "oom", "output": why the sandbox stopped it


def verdict(run: Run, expected: str, actual: str, limits: Limits, mode: str = "tokens") -> str:
    """Order: memory, time, output, crash, then the answer. A finished run that is over its limit is still over it."""
    crashed = run.signal != 0 or run.exit_code != 0
    if run.killed == "oom" or run.peak_kb > limits.mem_kb:
        return "MLE"
    if crashed and run.peak_kb >= limits.mem_kb * 0.98:   # a failed allocation shows up as a crash at the limit
        return "MLE"
    if run.killed in ("cpu", "wall") or run.cpu_s > limits.cpu_s:
        return "TLE"
    if run.killed == "output" or run.out_bytes > limits.out_bytes:
        return "OLE"
    if crashed:
        return "RE"
    return "AC" if compare(expected, actual, mode) else "WA"
```

Four decisions are this lesson's own policy, not a standard: memory is tested before time because an out-of-memory kill is deterministic while a time reading is noisy; a run that finished with the right answer at 1.0001 s against a 1.0 s limit is TLE (the limit is the limit); a crash within 2% of the memory limit is called MLE, because with an address-space limit the allocation fails (`isolate`'s `--mem`: "further memory allocations fail") and the program usually dies with a signal or a non-zero exit, which would otherwise read as a runtime error; the 2% tolerance is an assumption. The check compares `verdict` to a ranking reference on 3,000 random runs and pins the boundaries (exactly the limit is accepted).

### 6.3 Running it

The real mechanics need Linux (`rlimit`, cgroups); the runner below shows the part that is portable, and is run by the check against real child processes: a wall-clock limit, an output cap, and stdout redirected to a **file** rather than a pipe.

```python
import os, subprocess, tempfile, time


def run_case(argv, stdin_bytes: bytes, wall_s: float, out_limit: int, poll: float = 0.01):
    """Returns (killed, exit_code, output, wall_s). killed is "", "wall" or "output". Output is cut to out_limit.
    Wall time and output size only: CPU and memory limits belong to the sandbox (isolate --time, --mem, --fsize)."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as inp:
        inp.write(stdin_bytes)
        inp.seek(0)
        t0 = time.monotonic()
        p = subprocess.Popen(argv, stdin=inp, stdout=out, stderr=subprocess.DEVNULL)
        killed = ""
        while True:
            code = p.poll()
            if code is not None:
                break
            if time.monotonic() - t0 > wall_s:
                killed = "wall"
            elif os.fstat(out.fileno()).st_size > out_limit:
                killed = "output"
            if killed:
                p.kill()
                code = p.wait()
                break
            time.sleep(poll)
        wall = time.monotonic() - t0
        out.seek(0)
        data = out.read(out_limit + 1)
        if not killed and len(data) > out_limit:
            killed = "output"
        return killed, code, data[:out_limit], wall
```

Why a file: a grandchild that inherits a pipe keeps it open after its parent exits, and a reader waiting for end-of-file hangs the judge; the check starts a process that leaves a sleeping grandchild and requires the runner to return at once. The honest limits: the polling loop notices a flood after up to one poll interval, during which a fast writer has written to disk (the real guard is the file-size limit, which stops the write with SIGXFSZ), and `p.kill()` kills one process, not its tree (the real guard is the process limit and killing the control group). The check also requires that a busy loop and a sleeper are both stopped by the wall clock, and that output of exactly the limit is not an overflow while one byte more is.

---

## 7. Measuring Time

The `isolate` manual draws the line: `--time` counts CPU time ("time in which the OS assigns the processor to other tasks is not counted"), `--wall-time` counts the whole clock and is meant "as a precaution against sleeping programs" at "a much higher value". It also offers `--extra-time`: when the CPU limit is hit, wait a little longer before killing, "to report the real execution time, even if it exceeds the limit slightly". So: **CPU time is the main limit, wall time the backstop**, and the extra time lets you see whether a kill was 1.01 or 10 times the limit.

CPU time is still not a constant. Another process on the same core or cache, a frequency change or a cold file cache makes the same program measure slower; it almost never makes it faster. Three defences: a dedicated core and no other workload on the host (the manual's own advice), swap off, and **re-measure readings that are over the limit but not hopelessly so**, judging by the fastest reading:

```python
def judged_time(measure, limit: float, reruns: int = 2, hopeless: float = 2.0) -> float:
    """measure() returns one CPU-time reading. At or under the limit: final. Over it: re-measure up to `reruns`
    times unless it is more than `hopeless` x the limit; the verdict uses the fastest reading."""
    best = measure()
    if best <= limit or best > hopeless * limit:
        return best
    for _ in range(reruns):
        best = min(best, measure())
        if best <= limit:
            break
    return best
```

It rests on one assumption, labelled: noise only adds time. For the example (a solution whose true time is 0.8 of the limit, readings inflated by a factor 1 + an exponential with mean 0.1; both *assumed*), a single reading gives a false time-limit verdict with probability e^-2.5 = **8.2%**; with up to two re-measurements that falls to the cube, **0.055%**; and the cost is that submissions near the limit are run extra times, 8.2% + 8.2%^2 = **8.9%** of such submissions get at least one more reading. The check simulates 200,000 trials of each and compares with the closed forms, and shows a solution truly 5% over the limit never passes however many re-measurements it gets. The limit of the trick: it hides noise, not a solution that is honestly at the edge. A problem setter should leave a margin (a reference solution well inside the limit), and slow-but-correct languages need a multiplier, which is a product decision.

---

## 8. Scheduling a Burst

The worker fleet is a queue with many servers; FIFO is the default and the simulator below shows what it costs when one user floods it. Policy "fair" starts the next job of the user with the fewest jobs started so far (ties by arrival).

```python
import heapq


def simulate(jobs, workers: int, policy: str = "fifo"):
    """jobs: [(arrival, user, service)]. Returns {job_index: (start, finish)}. Work-conserving: a free worker never idles
    while a job has arrived. policy: "fifo" (arrival order) or "fair" (fewest jobs started by that user first)."""
    order = sorted(range(len(jobs)), key=lambda i: (jobs[i][0], i))
    free = [0.0] * workers
    heapq.heapify(free)
    waiting, started, res, nxt, clock = [], {}, {}, 0, 0.0
    while len(res) < len(jobs):
        s = max(heapq.heappop(free), clock)
        while nxt < len(order) and jobs[order[nxt]][0] <= s:
            waiting.append(order[nxt]); nxt += 1
        if not waiting:                                   # idle until the next arrival
            s = jobs[order[nxt]][0]
            while nxt < len(order) and jobs[order[nxt]][0] <= s:
                waiting.append(order[nxt]); nxt += 1
        if policy == "fifo":
            i = min(waiting, key=lambda k: (jobs[k][0], k))
        else:
            i = min(waiting, key=lambda k: (started.get(jobs[k][1], 0), jobs[k][0], k))
        waiting.remove(i)
        started[jobs[i][1]] = started.get(jobs[i][1], 0) + 1
        res[i] = (s, s + jobs[i][2])
        heapq.heappush(free, s + jobs[i][2])
        clock = s
    return res
```

The check compares both policies with a time-stepped reference on 300 random small workloads, and on every one verifies the invariants: no job starts before it arrives, no more than `workers` run at once, and no worker idles while a job waits.

**The example** (illustrative): 4 workers, 5 seconds per job; one user submits 40 jobs at time 0; eight other users submit one job each at time 1. FIFO starts four of the eight at 50 and four at 55, so they wait **49 seconds** and **54 seconds**. Fair sharing starts four of them at 5 and four at 10, so they wait **4 seconds** and **9 seconds**. The heavy user's own last job ends at 60 instead of 50, and **the makespan is 60 either way**: fair sharing reorders work, it creates no capacity. This is why the fleet must still be sized for the peak (section 3) and why the next defences are admission: a per-user limit on queued submissions, a minimum gap between submissions, and shedding (see Overload, Load Shedding and Cascading Failures).

**Known holes.** Fair sharing per user is defeated by many accounts, so the fairness key is sometimes IP or contest team. Shortest-job-first lowers average waits further but starves heavy jobs, which here means starving long-running problems. A contest wants the oldest first inside a user and fair across users, with practice submissions at lower priority, so a practice flood never delays a contest.

---

## 9. High-Level Design

1. **API** validates, stores the source, writes the submission, enqueues it, and returns the id. Polling or server push shows state; this is the "short-lived task" pattern.
2. **Queue** is durable with lease and retry; the dequeue order is the policy of section 8; a priority class per contest.
3. **Judge worker**: pulls a job, fetches the tests (cached by hash), compiles in a sandbox, runs tests in order in fresh sandboxes or one sandbox with cleanup, calls the checker, writes per-test results, stops at the first failure when the problem allows it.
4. **Results store and scoreboard**: the result row is final; the scoreboard consumes completion events (see Real-Time Gaming Leaderboard at 10M QPS).
5. **Rejudge**: a new submission version with the same source, for a changed test or checker; never overwrite history.

Workers are cattle: pinned to a core count, stateless except for the tests cache. Autoscale on the age of the oldest queued submission, not on CPU, because the work is bursty and the CPU of a worker waiting for a sandbox is not the signal.

---

## 10. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| worker dies mid-submission | the submission stays "running" | lease expiry and retry; result writes idempotent per test |
| fork bomb or memory bomb | a slow or dead worker | process and memory limits, one sandbox per core, kill the group |
| output flood | disk fills | file-size limit in the sandbox; a cap in the runner (section 6.3) |
| noisy neighbour on the host | false time-limit verdicts | dedicated hosts, re-measure near the limit |
| flood by one user | everyone else waits | fair queue, per-user admission limits (section 8) |
| peak above the fleet | an eight-minute verdict (section 3) | scale on queue age; shed practice work first |
| a stale tests cache | wrong verdicts after a test update | cache by content hash, never by name |
| checker bug | every submission to one problem is wrong | rejudge; run the reference solution against the checker before publishing |
| sandbox escape | the host is compromised | no secrets on workers, a stronger boundary, workers in their own network segment |

---

## 11. What Real Systems Did

The sources read here are infrastructure documentation, not judge operators.

- **isolate** (manual read 2026-11-27): a sandbox for "programs written by contestants", built on namespaces, control groups and rlimits, with the meta-file and limit set used in this lesson. The manual says nothing about which sites use it, and neither does this lesson.
- **gVisor** (documentation read 2026-11-27): the application-kernel approach, with the structural-versus-implementation cost split. **Firecracker** (Agache et al., NSDI 2020, read 2026-11-27): the AWS micro-VM manager behind Lambda and Fargate; the paper's use is serverless functions, not judging.
- **LeetCode, Codeforces and others:** no source read. The sizing and queue designs above are the general approach.

---

## 12. Pitfalls Checklist

1. **"It runs in Docker, so it is safe."** A container shares the host kernel; say what else you add.
2. **One time limit.** CPU time alone misses sleepers; wall time alone punishes a busy host.
3. **Counting the wrong memory.** An address-space limit counts memory a program only reserves; a cgroup limit counts page cache; swap lets a program go over. Say which you use and turn swap off.
4. **Comparing with `==` or `zip`.** Extra tokens, trailing whitespace, `1_0`, `nan` and `inf` all pass a careless checker.
5. **Verdict order left to chance.** Two limits broken, two different verdicts on rerun.
6. **Pipes for output.** A grandchild can hold a pipe open; use a file and a size cap, and kill the group.
7. **Sizing for the average.** The last ten minutes are the contest.
8. **FIFO with no per-user limit.** One user's flood is everyone's delay.
9. **Tests visible to the program.** Hidden tests in the sandbox file system are an answer key.
10. **Re-measuring without a floor.** Re-running everything over the limit makes hopeless programs cost three times; keep the `hopeless` cut.

---

## Drills

1. A submission prints the right answer but its CPU time is 1.003 s against a 1.0 s limit. What verdict, and what does `--extra-time` change about what you can report?
2. Why is CPU time the main limit and wall time the backstop? Which kind of program does each catch?
3. A program uses all of its memory limit and dies with a signal. Which verdict, and why can it not simply be RE?
4. Your runner reads the program's output through a pipe. Describe the program that hangs the judge, and the fix.
5. Name four layers of a sandbox and, for each, the threat it answers and what it does not stop.
6. When would you pick an application kernel or a micro-VM over a seccomp filter, and what is the cost of each?
7. Ten thousand users submit, a quarter of them in the last ten minutes. Work out the fleet size, and say what happens if you size for the average (use the lesson's figures).
8. One user queues 40 jobs ahead of eight others. How long do the eight wait under FIFO and under per-user fair sharing, and why does the heavy user still finish at the same total time?

---

## Homework

1. Run `sy60_check.py` on this file. Change `compare` to use `zip` without the length test and find the first failing assertion; then replace the numeric pattern with a bare `float()` call and find which fails.
2. Add a `lines` mode that also ignores leading spaces and decide, with a failing test, whether a problem statement could ever want that.
3. Extend `simulate` with a priority class (contest before practice) and check that practice submissions can starve; then add an age cap so they cannot.
4. Use `judged_time` with a measurement that has a heavy tail (a log-normal factor) and see where the closed forms in section 7 stop holding.
5. On a Linux machine, install `isolate`, run a program that forks, one that allocates 1 GB, and one that sleeps, and read the meta file for each.

---

## Sources

All read 2026-11-27. The runner, the verdict policy, the queue policies, the simulations and the figures marked *assumed* are this lesson's own.

- `isolate` manual (github.com/ioi/isolate, `isolate.1.txt`): read in full, including the resource options, control-group mode, meta-file and installation notes.
- gVisor documentation (gvisor.dev/docs): "What is gVisor?", the architecture guide introduction, the security model and the performance guide; read the parts on the application kernel, the threat model, CPU cost and system-call cost, not every page.
- Agache et al., *Firecracker: Lightweight Virtualization for Serverless Applications*, NSDI 2020 (usenix.org): abstract and introduction read; the evaluation was skimmed.
- Linux manual pages (man7.org): `seccomp(2)` (filter mode, `no_new_privs`, inheritance across `fork` and `execve`), `namespaces(7)` (the namespace kinds); and the kernel's cgroup v2 documentation (`memory.max`, `pids.max`), read for those controls only.

## Further reading (not consulted)

Any LeetCode, Codeforces, HackerRank or AtCoder engineering writing; the Judge0 and DOMjudge documentation; nsjail and bubblewrap; the Kubernetes sandbox runtime classes; checker conventions in testlib. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
