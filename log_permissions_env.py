"""Shared Docker log-directory permission fix for all experiment groups."""
from harbor.environments.docker.docker import DockerEnvironment


class WritableLogsDockerEnvironment(DockerEnvironment):
    async def start(self, force_build: bool):
        await super().start(force_build)

        if not self._is_windows_container:
            await self.exec(
                command=(
                    "mkdir -p /logs/agent /logs/verifier /logs/artifacts"
                    " && chmod 777 /logs/agent /logs/verifier /logs/artifacts"
                ),
                user="root",
            )
