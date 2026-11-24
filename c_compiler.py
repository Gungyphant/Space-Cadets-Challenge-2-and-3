import os
import random
import subprocess
import sys
import tempfile
from typing import Any, Callable

from errors import SyntacticalError, NegativeError, TimeoutError, _InnerCodeError
from extended import _de_extend_code
from main import ProcessedLine, Command, VariableDict, _process_program
from utils import format_time

C_START_BOILERPLATE = "#include <stdio.h>\n\nint main(void)\n{\n"
C_END_BOILERPLATE = "\n    return 0;\n}"

def _bb_to_c(code: list[ProcessedLine]) -> str:
    """Convert BB code to C code"""
    """Exit codes:
    0 - Successful
    non-zero n - NegativeError on line n
    """
    c_code = []
    variable_types = {}
    known_variables = set()
    depth = 1  # indent due to main()
    for line_no, line in enumerate(code):
        if not line:
            c_code.append("")
            continue
        command, variable_name, *others = line
        match command:
            case Command.INCR:
                c_code.append(f"{"    " * depth}{variable_name} += 1;")

            case Command.DECR:
                c_code.append(f"{"    " * depth}if ({variable_name} == 0) {{ return {line_no + 1}; }}")
                c_code.append(f"{"    " * depth}{variable_name} -= 1;")

            case Command.CLEAR:
                if variable_name not in known_variables:
                    # BB has no concept of scope; all variables must therefore be defined at the top
                    #  of the program
                    c_code = [f"    int {variable_name};"] + c_code
                    known_variables.add(variable_name)
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

    # Add stderr-writing to get the value of the variables
    for variable_name in known_variables:
        c_code.append(f"    fprintf(stderr, \"{variable_name}=%i\\n\", {variable_name});")

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


def _compile_c_file(c_filepath: str, executable_filepath: str | None = None, *, optimisation_level: int | None = None, output_warnings: bool = False) -> None:
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


def _run_exe(executable_filepath: str, *, timeout: float | None = None, discard_underscore_prefixed_variables: bool = False) -> VariableDict:
    """Run a BB program that has been compiled to an exe, and return the values of the variables"""
    # The executables write prints to stdout, and variable values to stderr; allow stdout to go to
    #  python's stdout (i.e. print it), but capture stderr into process_result:
    try:
        process_result = subprocess.run(executable_filepath, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        timeout: float
        raise _InnerCodeError(TimeoutError(f"The program exceeded the {format_time(timeout)} timeout"), -1, "")
    else:
        if process_result.returncode != 0:
            raise _InnerCodeError(NegativeError(f"Tried to decrement a variable that was already 0"), process_result.returncode, "")
        return {
            var: int(val)
            for var, val in (
                n.split("=")
                for n in
                process_result.stderr.decode(sys.stderr.encoding).split("\r\n")
                if n
                and not (discard_underscore_prefixed_variables and n.startswith("_"))
            )
        }


def __inner_execute_c_file(filepath: str, compiler: Callable[[str, str], None], timeout: float | None, kwargs: dict[str, Any], debug: bool, *, discard_underscore_prefixed_variables) -> dict[str, int]:
    try:
        compiler(filepath, "TEMP.c")
        _compile_c_file("TEMP.c", "TEMP.exe", **kwargs)
        result = _run_exe("TEMP.exe", timeout=timeout, discard_underscore_prefixed_variables=discard_underscore_prefixed_variables)
    except:
        if not debug:
            os.remove("TEMP.c")
            os.remove("TEMP.exe")
        raise
    else:
        os.remove("TEMP.c")
        os.remove("TEMP.exe")
    return result


def execute_file(filepath: str, *, timeout: float | None = None, debug: bool = False, **kwargs) -> VariableDict:
    """Execute a BB file, via compiling it to an executable

    :param filepath: The path to the BB file
    :param timeout: The timeout of the program execution
    :param debug: Toggles debug mode
    :param kwargs: Keyword-arguments passed onto :meth:`_compile_c_file`
    :return: A dictionary of variable-value pairs
    """
    return __inner_execute_c_file(filepath, compile_to_c_file, timeout, kwargs, debug, discard_underscore_prefixed_variables=False)


def execute_extended_file(filepath: str, *, timeout: float | None = None, debug: bool = False, **kwargs) -> VariableDict:
    """Execute a BBE file, via compiling it to an executable

    :param filepath: The path to the BBE file
    :param timeout: The timeout of the program execution
    :param debug: Toggles debug mode
    :param kwargs: Keyword-arguments passed onto :meth:`_compile_c_file`
    :return: A dictionary of variable-value pairs
    """
    return __inner_execute_c_file(filepath, extended_compile_to_c_file, timeout, kwargs, debug, discard_underscore_prefixed_variables=True)


_TEMP_DIR = tempfile.gettempdir()


def _test_compile_wrapper(code: list[str]) -> str:
    """Takes the BB code as a list of strings; returns the filepath to the exe"""
    id = random.randint(0, 100000)
    _bb_to_c_file(_process_program(code), f"{_TEMP_DIR}/{id}.c")
    _compile_c_file(f"{_TEMP_DIR}/{id}.c", f"{_TEMP_DIR}/{id}.exe", optimisation_level=3)
    return f"{_TEMP_DIR}/{id}.exe"



def _do_test():
    from testing_tools import run_all_tests, run_all_benchmarks
    run_all_tests(program_compiler=_test_compile_wrapper, program_executor=_run_exe, program_executor_kwargs={"timeout": 3, "discard_underscore_prefixed_variables": True}, test_file_location="BB files/De-extended Testing")
    print()
    run_all_benchmarks(program_compiler=_test_compile_wrapper, program_executor=_run_exe, program_executor_kwargs={"timeout": 3, "discard_underscore_prefixed_variables": True}, test_file_location="BB files/De-extended Testing")


if __name__ == "__main__":
    _do_test()
    # print(execute_file("BB files/Testing/01 Counting.bb", debug=True))
    # print(execute_extended_file("BB files/Hello, world!.bbe", debug=True))
    # print(execute_extended_file("BB files/Factorial.bbe", debug=True))
    # # execute_extended_file("BB files/Fibbonacci.bbe")
    #
    # extended_compile_to_c_file("BB files/Primes.bbe", "Primes.c")
