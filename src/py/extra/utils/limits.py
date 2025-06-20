from typing import NamedTuple, Annotated
import resource
from enum import Enum


class LimitType(Enum):
	Files = resource.RLIMIT_NOFILE
	Cores = resource.RLIMIT_CORE
	CPU = resource.RLIMIT_CPU
	FileSize = resource.RLIMIT_FSIZE
	Processes = resource.RLIMIT_NPROC


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


def unlimit(scope: LimitType, ratio: float = 1.0) -> int | bool:
	lm = limit(scope)
	try:
		target = int(lm.soft + ratio * (lm.hard - lm.soft))
		resource.setrlimit(scope.value, (target, lm.hard))
		return target
	except ValueError:
		return False
	except OSError:
		return False


# EOF
