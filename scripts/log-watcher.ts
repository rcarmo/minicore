/** Explicit opt-in user service: host log collector + presence observation; no Docker socket in management. */
import { join } from "node:path";
import { mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { root, loadTopology } from "./topology";
const [action] = process.argv.slice(2);
if (!["start", "stop", "restart", "status", "run"].includes(action))
  throw Error("Use start|stop|restart|status|run");
const unit = "minicore-logs.service";
async function systemctl(args: string[]) {
  const p = Bun.spawn(["systemctl", "--user", ...args], {
    stdout: "inherit",
    stderr: "inherit",
  });
  if (await p.exited) throw Error("systemctl failed");
}
if (action === "run") {
  await loadTopology();
  let stopping = false,
    collector: ReturnType<typeof Bun.spawn> | undefined,
    observer: ReturnType<typeof Bun.spawn> | undefined;
  const stop = () => {
    stopping = true;
    collector?.kill("SIGTERM");
    observer?.kill("SIGTERM");
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
  // systemd owns the process group and cleans all children on shutdown.
  const observe = async () => {
    while (!stopping) {
      observer = Bun.spawn(["bun", join(root, "scripts/lab.ts"), "observe"], {
        stdout: "ignore",
        stderr: "inherit",
      });
      await observer.exited;
      if (stopping) break;
      await Bun.sleep(3000);
    }
  };
  const observations = observe();
  try {
    while (!stopping) {
      collector = Bun.spawn(
        ["bun", join(root, "scripts/log-collector.ts"), "--duration", "3600"],
        { stdout: "inherit", stderr: "inherit" },
      );
      const exit = await collector.exited;
      if (exit && !stopping)
        throw Error("Collector failed; inspect its lock and service journal");
    }
  } finally {
    stop();
    await observations;
    process.off("SIGTERM", stop);
    process.off("SIGINT", stop);
  }
} else {
  if (action === "start" || action === "restart") {
    const directory = join(homedir(), ".config/systemd/user");
    await mkdir(directory, { recursive: true });
    if (/[\n\r%"\\]/.test(root) || /[\n\r%"\\]/.test(process.execPath))
      throw Error("Unsupported service path");
    await Bun.write(
      join(directory, unit),
      `[Unit]\nDescription=Minicore bounded node log and presence collector\nAfter=default.target\n\n[Service]\nType=simple\nWorkingDirectory=${root}\nExecStart="${process.execPath}" "${join(root, "scripts/log-watcher.ts")}" run\nEnvironment="PATH=${process.env.PATH}"\nKillMode=control-group\nTimeoutStopSec=12\nRestart=no\nUMask=0022\n\n[Install]\nWantedBy=default.target\n`,
    );
    await systemctl(["daemon-reload"]);
  }
  // Opt-in start, not enable: no unrequested boot persistence.
  await systemctl([action, unit]);
}
