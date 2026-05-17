"""JSON-backed project/device configuration."""

import json
import re
from copy import deepcopy
from pathlib import Path


CONFIG_VERSION = 1


def slugify(value, fallback):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value).strip().lower()).strip("-")
    return text or fallback


def default_project_config(defaults, paths):
    device_id = "jetson-default"
    project_id = "default-project"
    return {
        "version": CONFIG_VERSION,
        "active_device_id": device_id,
        "active_project_id": project_id,
        "devices": [
            {
                "id": device_id,
                "name": "Jetson Default",
                "type": "jetson",
                "ssh": defaults.remote,
                "proxy_host": "192.168.1.11",
                "proxy_port": defaults.proxy_port,
            }
        ],
        "projects": [
            {
                "id": project_id,
                "device_id": device_id,
                "name": "Default Project",
                "local_root": str(paths.project_dir if paths.project_dir.exists() else paths.app_dir),
                "remote_root": defaults.remote_path,
                "build_command": "cmake --build build -j4",
                "run_command": "python3 detect.py",
                "stop_pattern": "detect.py",
                "log_target": "run-control.log",
                "model_profiles": [
                    {
                        "id": "default-model",
                        "name": "Default Model",
                        "source": "model.onnx",
                        "output": "model.engine",
                        "precision": "fp16",
                        "test_image": "test.jpg",
                    }
                ],
            }
        ],
    }


class ProjectConfigStore:
    def __init__(self, path, defaults, paths):
        self.path = Path(path)
        self.defaults = defaults
        self.paths = paths
        self.was_created = not self.path.exists()
        self.needs_save = False
        self.data = self._load()
        self.normalize()
        if self.was_created or self.needs_save:
            self.save()

    def _load(self):
        if not self.path.exists():
            self.needs_save = True
            return default_project_config(self.defaults, self.paths)
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            backup = self.path.with_suffix(self.path.suffix + ".broken")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.needs_save = True
            return default_project_config(self.defaults, self.paths)

    def normalize(self):
        try:
            before = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            before = None

        if not isinstance(self.data, dict):
            self.data = default_project_config(self.defaults, self.paths)
        self.data["version"] = CONFIG_VERSION
        self.data.setdefault("devices", [])
        self.data.setdefault("projects", [])
        if not self.data["devices"]:
            self.data["devices"] = default_project_config(self.defaults, self.paths)["devices"]
        if not self.data["projects"]:
            self.data["projects"] = default_project_config(self.defaults, self.paths)["projects"]

        for index, device in enumerate(self.data["devices"]):
            device.setdefault("id", "device-{}".format(index + 1))
            device.setdefault("name", device["id"])
            device.setdefault("type", "linux")
            device.setdefault("ssh", self.defaults.remote)
            device.setdefault("proxy_host", "192.168.1.11")
            device.setdefault("proxy_port", self.defaults.proxy_port)

        first_device_id = self.data["devices"][0]["id"]
        for index, project in enumerate(self.data["projects"]):
            project.setdefault("id", "project-{}".format(index + 1))
            project.setdefault("device_id", first_device_id)
            project.setdefault("name", project["id"])
            project.setdefault("local_root", str(self.paths.app_dir))
            project.setdefault("remote_root", self.defaults.remote_path)
            project.setdefault("build_command", "cmake --build build -j4")
            project.setdefault("run_command", "python3 detect.py")
            project.setdefault("stop_pattern", "detect.py")
            project.setdefault("log_target", "run-control.log")
            project.setdefault("model_profiles", [])

        if not self.get_device(self.data.get("active_device_id")):
            self.data["active_device_id"] = first_device_id
        if not self.get_project(self.data.get("active_project_id")):
            self.data["active_project_id"] = self.data["projects"][0]["id"]

        try:
            after = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            after = None
        if before != after:
            self.needs_save = True

    def migrate_from_qsettings(self, settings):
        if not self.was_created:
            return
        device = self.active_device()
        project = self.active_project()
        if not device or not project:
            return

        device["ssh"] = str(settings.value("ssh/remote", device.get("ssh", self.defaults.remote)))
        device["proxy_host"] = str(settings.value("proxy/windows_ip", device.get("proxy_host", "192.168.1.11")))
        try:
            device["proxy_port"] = int(settings.value("proxy/port", device.get("proxy_port", self.defaults.proxy_port)))
        except (TypeError, ValueError):
            device["proxy_port"] = self.defaults.proxy_port

        project["remote_root"] = str(settings.value("ssh/remote_path", project.get("remote_root", self.defaults.remote_path)))
        project["local_root"] = str(settings.value("transfer/local_root", project.get("local_root", str(self.paths.app_dir))))
        project["run_command"] = str(settings.value("runtime/command", project.get("run_command", "python3 detect.py")))
        project["log_target"] = str(settings.value("logs/target", project.get("log_target", "run-control.log")))
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self.needs_save = False

    def devices(self):
        return self.data.get("devices", [])

    def projects(self, device_id=None):
        projects = self.data.get("projects", [])
        if device_id:
            return [project for project in projects if project.get("device_id") == device_id]
        return projects

    def get_device(self, device_id):
        for device in self.devices():
            if device.get("id") == device_id:
                return device
        return None

    def get_project(self, project_id):
        for project in self.projects():
            if project.get("id") == project_id:
                return project
        return None

    def active_device(self):
        return self.get_device(self.data.get("active_device_id"))

    def active_project(self):
        return self.get_project(self.data.get("active_project_id"))

    def set_active_device(self, device_id):
        if self.get_device(device_id):
            self.data["active_device_id"] = device_id
            projects = self.projects(device_id)
            if projects and not any(project.get("id") == self.data.get("active_project_id") for project in projects):
                self.data["active_project_id"] = projects[0]["id"]
            self.save()

    def set_active_project(self, project_id):
        project = self.get_project(project_id)
        if project:
            self.data["active_project_id"] = project_id
            self.data["active_device_id"] = project.get("device_id", self.data.get("active_device_id"))
            self.save()

    def upsert_device(self, device):
        item = deepcopy(device)
        item["id"] = item.get("id") or slugify(item.get("name"), "device")
        existing = self.get_device(item["id"])
        if existing:
            existing.update(item)
        else:
            self.data["devices"].append(item)
        self.data["active_device_id"] = item["id"]
        self.normalize()
        self.save()
        return item["id"]

    def delete_device(self, device_id):
        self.data["devices"] = [device for device in self.devices() if device.get("id") != device_id]
        self.data["projects"] = [project for project in self.projects() if project.get("device_id") != device_id]
        self.normalize()
        self.save()

    def upsert_project(self, project):
        item = deepcopy(project)
        item["id"] = item.get("id") or slugify(item.get("name"), "project")
        existing = self.get_project(item["id"])
        if existing:
            existing.update(item)
        else:
            self.data["projects"].append(item)
        self.data["active_project_id"] = item["id"]
        self.data["active_device_id"] = item.get("device_id", self.data.get("active_device_id"))
        self.normalize()
        self.save()
        return item["id"]

    def delete_project(self, project_id):
        self.data["projects"] = [project for project in self.projects() if project.get("id") != project_id]
        self.normalize()
        self.save()

    def upsert_model_profile(self, project_id, profile):
        project = self.get_project(project_id)
        if not project:
            return None
        item = deepcopy(profile)
        item["id"] = item.get("id") or slugify(item.get("name"), "model")
        profiles = project.setdefault("model_profiles", [])
        for existing in profiles:
            if existing.get("id") == item["id"]:
                existing.update(item)
                self.save()
                return item["id"]
        profiles.append(item)
        self.save()
        return item["id"]

    def delete_model_profile(self, project_id, profile_id):
        project = self.get_project(project_id)
        if not project:
            return
        project["model_profiles"] = [
            profile for profile in project.get("model_profiles", []) if profile.get("id") != profile_id
        ]
        self.save()

    def current_context(self):
        return {
            "device": deepcopy(self.active_device() or {}),
            "project": deepcopy(self.active_project() or {}),
        }
