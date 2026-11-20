import subprocess
import sys

from errors import SyntacticalError
from extended import _de_extend_code
from main import ProcessedLine, Command, VariableDict, _process_program

C_START_BOILERPLATE = "#include <stdio.h>\n\nint main(void)\n{\n"
C_END_BOILERPLATE = "\n    return 0;\n}"

def _bb_to_c(code: list[ProcessedLine]) -> str:
    """Convert BB code to C code"""
    """Exit codes:
    0 - Successful
    1 - NegativeError
    """
    c_code = []
    variable_types = {}
    known_variables = set()
    depth = 1  # indent due to main()
    for line in code:
        if not line:
            c_code.append("")
            continue
        command, variable_name, *others = line
        match command:
            case Command.INCR:
                c_code.append(f"{"    " * depth}{variable_name} += 1;")

            case Command.DECR:
                c_code.append(f"{"    " * depth}if ({variable_name} == 0) {{ return 1; }}")
                c_code.append(f"{"    " * depth}{variable_name} -= 1;")

            case Command.CLEAR:
                if variable_name not in known_variables:
                    c_code.append(f"{"    " * depth}int {variable_name} = 0;")
                    known_variables.add(variable_name)
                else:
                    c_code.append(f"{"    " * depth}{variable_name} = 0;")

            case Command.PRINT:
                if not variable_name:
                    # Bare print
                    c_code.append(f"{"    " * depth}printf(\"\\n\");")
                elif variable_name not in variable_types:
                    # int
                    c_code.append(f"{"    " * depth}printf(\"%i\\n\", {variable_name});")
                else:
                    match variable_types[variable_name]:
                        case "char":
                            c_code.append(f"{"    " * depth}printf(\"%c\", (char) {variable_name});")
                        case "bit vector":
                            c_code.append(f"{"    " * depth}printf(\"[bit vector]%i\\n\", {variable_name});")

            case Command.WHILE:
                c_code.append(f"{"    " * depth}while ({variable_name} != 0) {{")
                depth += 1

            case Command.END:
                depth -= 1
                c_code.append(f"{"    " * depth}}}")

            case Command.TYPE:
                type = others[0]
                if type == "int":
                    variable_types.pop(variable_name)  # variables are ints if not specified
                else:
                    variable_types[variable_name] = type

            case _:
                raise ValueError(f"Unexpected Command {command}")

    return C_START_BOILERPLATE + "\n".join(c_code) + C_END_BOILERPLATE


def _bb_to_c_file(code: list[ProcessedLine], c_filepath: str) -> None:
    """Convert BB code to C code and write it to a file"""
    c_code = _bb_to_c(code)
    with open(c_filepath, "w") as f:
        f.write(c_code)


def compile_to_c_file(bb_filepath: str, c_filepath: str) -> None:
    """Compile a Bare Bones file to a C file"""
    with open(bb_filepath) as f:
        bare_bones_file = f.read()
    _bb_to_c_file(_process_program(bare_bones_file), c_filepath)


def extended_compile_to_c_file(bbe_filepath: str, c_filepath: str) -> None:
    """Compiles a Bare Bones Extended file to a C file"""
    with open(bbe_filepath) as f:
        bare_bones_extended_file = f.read()
    bare_bones_file = _de_extend_code(bare_bones_extended_file.splitlines())
    _bb_to_c_file(_process_program(bare_bones_file), c_filepath)


def compile_c_file(c_filepath: str, executable_filepath: str | None = None, *, optimisation_level: int | None = None, output_warnings: bool = False) -> None:
    """Compile a C program to an executable

    Note: gcc must be in your PATH to use this function

    :param c_filepath: The filepath of the C program to compile
    :param executable_filepath: The filepath of the compiled executable; if None, gcc's default is used
    :param optimisation_level: The level of gcc optimisation to use; if None, gcc's default is used
    :param output_warnings: Should gcc warnings be printed
    """
    command = (
        f"cls & "  # Allow for ignoring of startup command outputs
        f"gcc "
        f"{f"-O{optimisation_level} " if optimisation_level is not None else ""}"
        f"{f"-Wall " if output_warnings else ""}"
        f"\"{c_filepath}\""
        f"{f" -o \"{executable_filepath}\"" if executable_filepath is not None else ""}"
       )

    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode != 0:
        # Failed to compile
        raise SyntacticalError(result.stderr.decode(sys.stdout.encoding))
    if output_warnings:
        print(result.stdout.decode(sys.stdout.encoding).split("\x0c")[-1], end="")
