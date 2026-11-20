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
