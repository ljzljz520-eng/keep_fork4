"""Optional runtime environment contract for saved commands.

A contract is *portable*: it only declares what a command needs
(operating system, architecture, shell dialect, working directory
policy, executables, environment variables, paths). It never stores
machine specific probe results.

Entries without a contract are "undeclared" and evaluate to
``UNKNOWN`` -- they are never assumed to be compatible.

Local, non portable adaptations (different paths, env values, ...)
live in ``~/.keep/local_overrides.json`` and are never synced.
"""
import json
import os
import platform
import re
import shlex
import shutil

from keep import utils

# Evaluation outcomes (ordered from safest to act on, to least).
COMPATIBLE = 'compatible'
UNKNOWN = 'unknown'
INCOMPATIBLE = 'incompatible'

# Contract keys that are allowed in a portable declaration.
CONTRACT_KEYS = ('os', 'arch', 'shell', 'cwd', 'executables', 'env', 'paths')

_OS_ALIASES = {
    'darwin': 'darwin', 'macos': 'darwin', 'mac': 'darwin',
    'osx': 'darwin', 'macosx': 'darwin',
    'linux': 'linux',
    'windows': 'windows', 'win32': 'windows', 'win': 'windows',
    'freebsd': 'freebsd', 'openbsd': 'openbsd', 'netbsd': 'netbsd',
}

_ARCH_ALIASES = {
    'x86_64': 'x86_64', 'amd64': 'x86_64', 'x64': 'x86_64',
    'arm64': 'arm64', 'aarch64': 'arm64',
    'x86': 'x86', 'i386': 'x86', 'i686': 'x86', 'i486': 'x86',
    'i586': 'x86', '386': 'x86',
    'armv7l': 'armv7l', 'armv6l': 'armv6l',
    'riscv64': 'riscv64', 'ppc64le': 'ppc64le', 's390x': 's390x',
}

_SHELL_ALIASES = {
    'sh': 'sh', 'dash': 'sh',
    'bash': 'bash',
    'zsh': 'zsh',
    'fish': 'fish',
    'pwsh': 'pwsh', 'powershell': 'pwsh',
    'cmd': 'cmd',
    'nu': 'nu', 'csh': 'csh', 'tcsh': 'tcsh',
}

_TOKEN_RE = re.compile(r'^[a-z0-9_.+-]+$')
_PATH_TYPES = ('file', 'dir', 'any')


# --------------------------------------------------------------------------
# Local probing. Results are used to suggest a contract and to evaluate
# one, but they must never be written into commands.json.
# --------------------------------------------------------------------------

def probe_environment():
    """Returns a dict describing the current machine.

    The dict is intentionally shaped like a (superset of a) contract,
    but values are scalars. ``shell`` may be ``None`` when it cannot be
    determined.
    """
    return {
        'os': current_os(),
        'arch': current_arch(),
        'shell': current_shell(),
        'cwd': os.getcwd(),
    }


def current_os():
    return platform.system().lower()


def current_arch():
    machine = platform.machine().lower()
    return _ARCH_ALIASES.get(machine, machine)


def current_shell():
    """Best-effort detection of the shell dialect of the invoking user."""
    shell = os.environ.get('SHELL')
    if shell:
        name = os.path.basename(shell).lower()
        if name.endswith('.exe'):
            name = name[:-4]
        return _SHELL_ALIASES.get(name, name)
    if os.name == 'nt':
        if os.environ.get('PSMODULEPATH'):
            return 'pwsh'
        comspec = os.environ.get('COMSPEC')
        if comspec:
            name = os.path.basename(comspec).lower()
            if name.endswith('.exe'):
                name = name[:-4]
            return _SHELL_ALIASES.get(name, name)
    return None


def minimal_contract(cmd=''):
    """Builds a minimal, editable contract from the current environment.

    Only highly confident facts are included: the operating system,
    architecture, shell dialect, and (when inferable) the executable
    the command starts with.
    """
    env = probe_environment()
    contract = {
        'os': [env['os']],
        'arch': [env['arch']],
    }
    if env['shell']:
        contract['shell'] = [env['shell']]

    executable = _infer_executable(cmd)
    if executable:
        contract['executables'] = [executable]
    return contract


def _infer_executable(cmd):
    if not cmd:
        return None
    try:
        tokens = shlex.split(cmd, posix=(os.name != 'nt'))
    except ValueError:
        return None
    if not tokens:
        return None
    token = os.path.basename(tokens[0])
    if not token or token in ('cd', 'export', 'unset', 'set', 'source',
                              'echo', 'eval', 'exec'):
        return None
    if shutil.which(token):
        return token
    return None


# --------------------------------------------------------------------------
# Cleaning / validation of a portable declaration.
# --------------------------------------------------------------------------

def _as_list(value, kind):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ValueError("'{}' must be a non empty list".format(kind))
    return value


def _normalize_token(value, aliases, kind, permit_unknown=False):
    if not isinstance(value, str) or not value:
        raise ValueError("'{}' entries must be non empty strings"
                         .format(kind))
    token = value.strip().lower()
    token = aliases.get(token, token)
    if not _TOKEN_RE.match(token):
        raise ValueError("unknown {} value '{}'".format(kind, value))
    if not permit_unknown and token not in aliases.values():
        raise ValueError("unknown {} value '{}'".format(kind, value))
    return token


def clean_contract(raw):
    """Validates and normalizes a contract dict.

    Raises ValueError with a descriptive message on invalid data.
    Returns a new dict containing only portable, canonical fields.
    An empty dict is a valid explicit "no constraints" declaration.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("contract must be an object")

    unknown = set(raw) - set(CONTRACT_KEYS)
    if unknown:
        raise ValueError("unknown contract field(s): {}"
                         .format(', '.join(sorted(unknown))))

    cleaned = {}

    if 'os' in raw:
        values = [_normalize_token(v, _OS_ALIASES, 'os')
                  for v in _as_list(raw['os'], 'os')]
        cleaned['os'] = sorted(set(values))

    if 'arch' in raw:
        values = [_normalize_token(v, _ARCH_ALIASES, 'arch',
                                   permit_unknown=True)
                  for v in _as_list(raw['arch'], 'arch')]
        cleaned['arch'] = sorted(set(values))

    if 'shell' in raw:
        values = [_normalize_token(v, _SHELL_ALIASES, 'shell',
                                   permit_unknown=True)
                  for v in _as_list(raw['shell'], 'shell')]
        cleaned['shell'] = sorted(set(values))

    if 'executables' in raw:
        values = _as_list(raw['executables'], 'executables')
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("'executables' entries must be non empty "
                                 "strings")
        cleaned['executables'] = values

    if 'env' in raw:
        env = raw['env']
        if not isinstance(env, dict) or not env:
            raise ValueError("'env' must be a non empty object of "
                             "VAR: pattern (use '' for present-only)")
        for name, pattern in env.items():
            if not isinstance(name, str) or not name:
                raise ValueError("env variable names must be non empty "
                                 "strings")
            if not isinstance(pattern, str):
                raise ValueError("env requirement for '{}' must be a regex "
                                 "string ('' for present-only)".format(name))
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as err:
                    raise ValueError("invalid regex for '{}': {}".format(
                        name, err))
        cleaned['env'] = dict(env)

    if 'paths' in raw:
        paths = _as_list(raw['paths'], 'paths')
        cleaned_paths = []
        for entry in paths:
            if isinstance(entry, str):
                if not entry:
                    raise ValueError("'paths' entries must be non empty "
                                     "strings")
                cleaned_paths.append({'path': entry, 'type': 'any'})
            elif isinstance(entry, dict):
                path = entry.get('path')
                ptype = entry.get('type', 'any')
                if not isinstance(path, str) or not path:
                    raise ValueError("path objects need a non empty 'path'")
                if ptype not in _PATH_TYPES:
                    raise ValueError("path type must be one of {}".format(
                        ', '.join(_PATH_TYPES)))
                cleaned_paths.append({'path': path, 'type': ptype})
            else:
                raise ValueError("'paths' entries must be strings or "
                                 "objects")
        cleaned['paths'] = cleaned_paths

    if 'cwd' in raw:
        cleaned['cwd'] = _clean_cwd(raw['cwd'])

    return cleaned


def _clean_cwd(cwd):
    if isinstance(cwd, str):
        if cwd not in ('any', 'git'):
            raise ValueError("cwd string must be 'any' or 'git'")
        return cwd
    if isinstance(cwd, dict):
        keys = [key for key in ('path', 'under') if key in cwd]
        if len(keys) != 1:
            raise ValueError("cwd object needs exactly one of 'path' or "
                             "'under'")
        target = cwd[keys[0]]
        if not isinstance(target, str) or not target:
            raise ValueError("cwd '{}' must be a non empty path"
                             .format(keys[0]))
        return {keys[0]: target}
    raise ValueError("cwd must be 'any', 'git', {'path': ...} or "
                     "{'under': ...}")


# --------------------------------------------------------------------------
# Deterministic evaluation.
# --------------------------------------------------------------------------

class CheckResult(object):
    def __init__(self, scope, detail, status):
        self.scope = scope
        self.detail = detail
        self.status = status

    def __repr__(self):
        return 'CheckResult({!r}, {!r}, {!r})'.format(
            self.scope, self.detail, self.status)


def evaluate_contract(contract, overrides=None, cwd=None):
    """Evaluates a contract against the current machine.

    Returns ``(status, checks)`` where status is one of COMPATIBLE,
    UNKNOWN, INCOMPATIBLE and checks is a list of CheckResult.
    INCOMPATIBLE takes precedence over UNKNOWN: a deterministically
    failing requirement cannot be rescued by another unknown one.
    """
    overrides = overrides or {}
    if cwd is None:
        cwd = os.getcwd()

    if not contract:
        return UNKNOWN, [CheckResult('contract', 'no environment contract '
                                     'declared', UNKNOWN)]

    # Normalize first so hand edited JSON (single strings, path
    # shorthands, ...) evaluates the same way as generated entries.
    try:
        contract = clean_contract(contract)
    except ValueError as err:
        return UNKNOWN, [CheckResult('contract',
                                     'invalid environment contract: {}'
                                     .format(err), UNKNOWN)]

    checks = []
    checks += _check_membership('os', contract.get('os'), current_os())
    checks += _check_membership('arch', contract.get('arch'),
                                current_arch())
    checks += _check_shell(contract.get('shell'))
    checks += _check_executables(contract.get('executables'), overrides)
    checks += _check_env(contract.get('env'), overrides)
    checks += _check_paths(contract.get('paths'), overrides)
    checks += _check_cwd(contract.get('cwd'), overrides, cwd)

    statuses = [check.status for check in checks]
    if INCOMPATIBLE in statuses:
        status = INCOMPATIBLE
    elif UNKNOWN in statuses:
        status = UNKNOWN
    else:
        status = COMPATIBLE
    return status, checks


def _check_membership(scope, allowed, actual):
    if not allowed:
        return []
    if actual in allowed:
        return [CheckResult(scope, '{} is supported'.format(actual),
                            COMPATIBLE)]
    return [CheckResult(scope, "{} '{}' is not in {}".format(
        scope, actual, ', '.join(allowed)), INCOMPATIBLE)]


def _check_shell(allowed):
    if not allowed:
        return []
    shell = current_shell()
    if shell is None:
        return [CheckResult('shell', 'current shell could not be detected',
                            UNKNOWN)]
    if shell in allowed:
        return [CheckResult('shell', '{} is supported'.format(shell),
                            COMPATIBLE)]
    return [CheckResult('shell', "shell '{}' is not in {}".format(
        shell, ', '.join(allowed)), INCOMPATIBLE)]


def _check_executables(spec, overrides):
    if not spec:
        return []
    override_map = overrides.get('executables', {})
    checks = []
    for name in spec:
        target = override_map.get(name, name)
        resolved = _expand(target)
        if not _is_resolved(target, resolved):
            checks.append(CheckResult('executable',
                                      "{} resolves via unset variable"
                                      .format(name), UNKNOWN))
        elif shutil.which(resolved):
            checks.append(CheckResult(
                'executable',
                '{} found'.format(name) + (
                    '' if resolved == name else ' at {}'.format(resolved)),
                COMPATIBLE))
        else:
            checks.append(CheckResult('executable',
                                      "required executable '{}' was not "
                                      "found on PATH".format(name),
                                      INCOMPATIBLE))
    return checks


def _check_env(spec, overrides):
    if not spec:
        return []
    override_map = overrides.get('env', {})
    checks = []
    for name, pattern in spec.items():
        if name in override_map:
            value = _expand(override_map[name])
            source = 'override'
        elif name in os.environ:
            value = os.environ[name]
            source = 'environment'
        else:
            checks.append(CheckResult(
                'env', "required environment variable '{}' is not set"
                .format(name), INCOMPATIBLE))
            continue
        if not pattern:
            checks.append(CheckResult('env', "'{}' is set ({})".format(
                name, source), COMPATIBLE))
        elif re.search(pattern, value):
            checks.append(CheckResult('env', "'{}' matches {!r} ({})".format(
                name, pattern, source), COMPATIBLE))
        else:
            checks.append(CheckResult(
                'env', "'{}' value does not match {!r}".format(name,
                                                               pattern),
                INCOMPATIBLE))
    return checks


def _check_paths(spec, overrides):
    if not spec:
        return []
    override_map = overrides.get('paths', {})
    checks = []
    for entry in spec:
        declared = entry['path']
        ptype = entry['type']
        target = override_map.get(declared, declared)
        resolved = _expand(target)
        if not _is_resolved(target, resolved):
            checks.append(CheckResult('path',
                                      "{} contains an unset variable"
                                      .format(declared), UNKNOWN))
            continue
        if not os.path.exists(resolved):
            checks.append(CheckResult(
                'path', "required path '{}' does not exist".format(
                    declared), INCOMPATIBLE))
            continue
        if ptype == 'file' and not os.path.isfile(resolved):
            checks.append(CheckResult(
                'path', "'{}' exists but is not a file".format(declared),
                INCOMPATIBLE))
        elif ptype == 'dir' and not os.path.isdir(resolved):
            checks.append(CheckResult(
                'path', "'{}' exists but is not a directory".format(
                    declared), INCOMPATIBLE))
        else:
            detail = "'{}' exists".format(declared)
            if target != declared:
                detail += ' (local override)'
            checks.append(CheckResult('path', detail, COMPATIBLE))
    return checks


def _check_cwd(spec, overrides, cwd):
    if not spec:
        return []
    if spec == 'any':
        return [CheckResult('cwd', 'any working directory accepted',
                            COMPATIBLE)]
    if spec == 'git':
        if _find_git_root(cwd):
            return [CheckResult('cwd', 'inside a git repository',
                                COMPATIBLE)]
        return [CheckResult('cwd', 'not inside a git repository',
                            INCOMPATIBLE)]

    override_map = overrides.get('cwd', {})
    if 'path' in spec:
        declared = spec['path']
        target = override_map.get(declared, declared)
        resolved = _expand(target)
        if not _is_resolved(target, resolved):
            return [CheckResult('cwd',
                                'cwd path contains an unset variable',
                                UNKNOWN)]
        if os.path.realpath(cwd) == os.path.realpath(resolved):
            return [CheckResult('cwd', 'working directory matches {}'.format(
                resolved), COMPATIBLE)]
        return [CheckResult('cwd', "working directory is not '{}'".format(
            resolved), INCOMPATIBLE)]

    declared = spec['under']
    target = override_map.get(declared, declared)
    resolved = _expand(target)
    if not _is_resolved(target, resolved):
        return [CheckResult('cwd', 'cwd path contains an unset variable',
                            UNKNOWN)]
    if not os.path.isdir(resolved):
        return [CheckResult('cwd', "required base directory '{}' does not "
                                   "exist".format(declared), INCOMPATIBLE)]
    if _is_within(cwd, resolved):
        return [CheckResult('cwd', 'working directory is under {}'.format(
            resolved), COMPATIBLE)]
    return [CheckResult('cwd', "working directory is not under '{}'".format(
        resolved), INCOMPATIBLE)]


def _find_git_root(path):
    current = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _is_within(path, base):
    try:
        return os.path.commonpath([os.path.realpath(path),
                                   os.path.realpath(base)]) == \
            os.path.realpath(base)
    except ValueError:
        return False


def _expand(value):
    return os.path.expandvars(os.path.expanduser(value))


def _is_resolved(raw, expanded):
    if '$' in raw and raw == expanded:
        return False
    return bool(expanded)


# --------------------------------------------------------------------------
# Local overrides (never synced).
# --------------------------------------------------------------------------

OVERRIDES_FILENAME = 'local_overrides.json'
_OVERRIDE_SECTIONS = ('paths', 'env', 'executables', 'cwd')


def overrides_path():
    return os.path.join(utils.dir_path, OVERRIDES_FILENAME)


def read_overrides():
    path = overrides_path()
    if not os.path.exists(path):
        return {}
    try:
        raw = json.loads(open(path, 'r').read())
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    overrides = {}
    for section in _OVERRIDE_SECTIONS:
        value = raw.get(section, {})
        if isinstance(value, dict):
            overrides[section] = {
                k: v for k, v in value.items()
                if isinstance(k, str) and isinstance(v, str)}
    return overrides


def write_overrides(overrides):
    path = overrides_path()
    with open(path, 'w') as override_file:
        json.dump(overrides, override_file, indent=2, sort_keys=True)


def clean_overrides(raw):
    """Validates an overrides document. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("overrides must be an object")
    unknown = set(raw) - set(_OVERRIDE_SECTIONS)
    if unknown:
        raise ValueError("unknown override section(s): {}".format(
            ', '.join(sorted(unknown))))
    cleaned = {}
    for section in _OVERRIDE_SECTIONS:
        value = raw.get(section, {})
        if not isinstance(value, dict):
            raise ValueError("section '{}' must be an object".format(section))
        mapping = {}
        for key, target in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("keys in '{}' must be non empty strings"
                                 .format(section))
            if not isinstance(target, str):
                raise ValueError("override target for '{}' must be a string"
                                 .format(key))
            mapping[key] = target
        if mapping:
            cleaned[section] = mapping
    return cleaned


# --------------------------------------------------------------------------
# Applying local adaptations at execution time (POSIX shells only).
# --------------------------------------------------------------------------

def resolve_cwd_target(contract, overrides):
    """Returns a directory to run in, or None.

    Only an exact cwd 'path' policy can be resolved to a concrete
    directory; 'git'/'under' policies cannot pick one unambiguously.
    """
    if not contract or not isinstance(contract.get('cwd'), dict):
        return None
    spec = contract['cwd']
    if 'path' not in spec:
        return None
    target = overrides.get('cwd', {}).get(spec['path'], spec['path'])
    resolved = _expand(target)
    if os.path.isdir(resolved):
        return resolved
    return None


def adapt_command(final_cmd, contract, overrides, posix=None):
    """Wraps a command so local override mappings take effect.

    Environment overrides are exported, executable overrides contribute
    their directories to PATH, and an exact cwd policy produces a
    leading ``cd``. Only POSIX /bin/sh syntax is emitted; on other
    platforms the command is returned unchanged (preflight still
    applies).
    """
    if posix is None:
        posix = os.name == 'posix'
    if not posix or not overrides:
        return final_cmd

    parts = []

    cwd_target = resolve_cwd_target(contract or {}, overrides)
    if cwd_target and os.path.realpath(cwd_target) != \
            os.path.realpath(os.getcwd()):
        parts.append('cd {}'.format(shlex.quote(cwd_target)))

    for name, value in overrides.get('env', {}).items():
        parts.append('{}={}'.format(name, shlex.quote(_expand(value))))

    extra_path_dirs = []
    for _, target in overrides.get('executables', {}).items():
        resolved = _expand(target)
        directory = resolved if os.path.isdir(resolved) else \
            os.path.dirname(resolved)
        if directory and directory not in extra_path_dirs:
            extra_path_dirs.append(directory)
    if extra_path_dirs:
        quoted = ':'.join(shlex.quote(directory)
                          for directory in extra_path_dirs)
        parts.append('PATH={}:$PATH'.format(quoted))

    if not parts:
        return final_cmd
    return '{} && {}'.format(' && '.join(parts), final_cmd)
