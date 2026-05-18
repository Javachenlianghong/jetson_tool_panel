"""Paramiko-backed SSH shell and SFTP helpers."""

import posixpath
import stat
from dataclasses import dataclass
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover - exercised at runtime when dependency is missing.
    paramiko = None


@dataclass(frozen=True)
class RemoteTarget:
    user: str
    host: str
    port: int = 22

    @property
    def display(self):
        if self.port == 22:
            return "{}@{}".format(self.user, self.host)
        return "{}@{}:{}".format(self.user, self.host, self.port)


def parse_remote_target(remote, default_user="jetson"):
    text = str(remote or "").strip()
    if not text:
        raise ValueError("远端 SSH 地址为空")

    user = default_user
    host_port = text
    if "@" in text:
        user, host_port = text.split("@", 1)
        user = user.strip() or default_user

    host = host_port.strip()
    port = 22
    if host_port.count(":") == 1 and not host_port.startswith("["):
        host_part, port_part = host_port.rsplit(":", 1)
        if port_part.isdigit():
            host = host_part.strip()
            port = int(port_part)

    if host.startswith("[") and "]" in host:
        host_part, rest = host[1:].split("]", 1)
        host = host_part
        if rest.startswith(":") and rest[1:].isdigit():
            port = int(rest[1:])

    if not host:
        raise ValueError("远端主机为空")
    if port < 1 or port > 65535:
        raise ValueError("SSH 端口不合法")
    return RemoteTarget(user=user, host=host, port=port)


def ensure_paramiko():
    if paramiko is None:
        raise RuntimeError("缺少 Paramiko 依赖，请先安装 requirements.txt。")
    return paramiko


def _known_hosts_path():
    return Path.home() / ".ssh" / "known_hosts"


def _accept_new_host_key_policy(filename):
    module = ensure_paramiko()

    class AcceptNewHostKeyPolicy(module.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            client._host_keys.add(hostname, key.get_name(), key)
            client._accepted_unknown_host = hostname
            try:
                client.save_host_keys(filename)
            except OSError as exc:
                client._host_key_save_error = str(exc)

    return AcceptNewHostKeyPolicy()


def create_ssh_client(remote, password=None, timeout=10):
    module = ensure_paramiko()
    target = parse_remote_target(remote)
    client = module.SSHClient()
    client._accepted_unknown_host = None
    client._host_key_save_error = None
    client.load_system_host_keys()
    known_hosts = _known_hosts_path()
    try:
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        known_hosts.touch(exist_ok=True)
        client.load_host_keys(str(known_hosts))
    except OSError as exc:
        client._host_key_save_error = str(exc)
    client.set_missing_host_key_policy(_accept_new_host_key_policy(str(known_hosts)))
    client.connect(
        target.host,
        port=target.port,
        username=target.user,
        password=password,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=True,
        allow_agent=True,
    )
    return client, target


def decode_ssh_bytes(data):
    for encoding in ("utf-8", "gb18030", "mbcs"):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("utf-8", errors="replace")


def permission_text(mode):
    file_type = "d" if stat.S_ISDIR(mode) else "-"
    bits = []
    for shift in (6, 3, 0):
        value = (mode >> shift) & 0b111
        bits.append("r" if value & 0b100 else "-")
        bits.append("w" if value & 0b010 else "-")
        bits.append("x" if value & 0b001 else "-")
    return file_type + "".join(bits)


def sftp_attr_to_item(name, attr):
    mode = int(getattr(attr, "st_mode", 0) or 0)
    return {
        "name": name,
        "is_dir": stat.S_ISDIR(mode),
        "size": int(getattr(attr, "st_size", 0) or 0),
        "mtime": int(getattr(attr, "st_mtime", 0) or 0),
        "mode": mode,
        "permission": permission_text(mode),
    }


def parent_remote_path(path):
    cleaned = str(path or "").strip() or "."
    parent = posixpath.dirname(cleaned.rstrip("/"))
    return parent or "/"


def join_remote_path(base, name):
    base = str(base or "").strip() or "."
    if base == "/":
        return "/" + name
    return posixpath.normpath(posixpath.join(base, name))


def local_item(path):
    item_path = Path(path)
    stat_result = item_path.stat()
    return {
        "name": item_path.name,
        "path": str(item_path),
        "is_dir": item_path.is_dir(),
        "size": stat_result.st_size,
        "mtime": int(stat_result.st_mtime),
        "permission": "<DIR>" if item_path.is_dir() else "",
    }


def iter_local_transfer_sources(paths):
    for source, relative, is_dir in iter_local_transfer_entries(paths):
        if not is_dir:
            yield source, relative


def iter_local_transfer_entries(paths):
    for raw_path in paths:
        source = Path(raw_path)
        if not source.exists():
            continue
        if source.is_file():
            yield source, source.name, False
            continue
        yield source, source.name, True
        for child in source.rglob("*"):
            relative = str(child.relative_to(source.parent)).replace("\\", "/")
            yield child, relative, child.is_dir()


def ensure_remote_dir(sftp, remote_dir):
    parts = [part for part in str(remote_dir).split("/") if part]
    current = "/" if str(remote_dir).startswith("/") else "."
    for part in parts:
        current = join_remote_path(current, part)
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def remote_walk_files(sftp, remote_path):
    for path, relative, is_dir in remote_walk_entries(sftp, remote_path):
        if not is_dir:
            yield path, relative


def remote_walk_entries(sftp, remote_path):
    attr = sftp.stat(remote_path)
    if not stat.S_ISDIR(attr.st_mode):
        yield remote_path, posixpath.basename(remote_path), False
        return
    root_parent = parent_remote_path(remote_path)
    yield remote_path, posixpath.relpath(remote_path, root_parent), True
    stack = [remote_path]
    while stack:
        current = stack.pop()
        for attr in sftp.listdir_attr(current):
            child = join_remote_path(current, attr.filename)
            rel = posixpath.relpath(child, root_parent)
            if stat.S_ISDIR(attr.st_mode):
                yield child, rel, True
                stack.append(child)
            else:
                yield child, rel, False
