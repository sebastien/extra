from typing import NamedTuple, Annotated
from enum import Enum
import resource


class LimitType(Enum):
	Files = resource.RLIMIT_NOFILE
	Cores = resource.RLIMIT_CORE
	CPU = resource.RLIMIT_CPU
	FileSize = resource.RLIMIT_FSIZE
	Processes = resource.RLIMIT_NPROC


REASONABLE_LIMITS: dict[LimitType, int] = {
	LimitType.Files: 10
	* 10240,  # Minimum recommended for production servers handling multiple connections
	LimitType.Cores: 0,  # Disable core dumps to save disk space in production
	LimitType.CPU: 3600,  # 1 hour soft limit to prevent runaway processes
	LimitType.FileSize: int(1e12),  # 1 TB to cap large file creations like logs
	LimitType.Processes: 4096,  # Supports multiple workers without risking overload
}


class Limit(NamedTuple):
	type: LimitType
	soft: int
	hard: int


class Limits:
	cores: Annotated[Limit, LimitType.Cores]
	cpu: Annotated[Limit, LimitType.CPU]
	files: Annotated[Limit, LimitType.Files]
	fileSize: Annotated[Limit, LimitType.FileSize]
	processes: Annotated[Limit, LimitType.Processes]


def limit(scope: LimitType) -> Limit:
	return Limit(scope, *resource.getrlimit(scope.value))


def unlimit(
	scope: LimitType, ratio: float = 1.0, *, maximum: int | None = 0
) -> int | bool:
	lm = limit(scope)
	try:
		target = int(lm.soft + ratio * (lm.hard - lm.soft))
		# We apply reasonable limits, as for instance Darwin has really high
		# limits that will lead to OverflowErrors.
		maximum = REASONABLE_LIMITS.get(scope) if maximum == 0 else maximum
		if maximum:
			target = min(maximum, target)
		resource.setrlimit(scope.value, (target, lm.hard))
		return target
	except ValueError:
		return False
	except OSError:
		return False


# EOF
