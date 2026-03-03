from langchain_core.tools import Tool
import sys
import io
import contextlib
import traceback
import os

def execute_python_code(query: str) -> str:
    """
    Ejecuta el bloque de código Python localmente y devuelve la salida.
    """
    print(f"👨‍💻 Ejecutando código dinámicamente:\n{query[:100]}...")
    
    # Limpiamos wrappers comunes si el LLM los incluyó por error
    code = query.strip()
    
    # 1. Quitar bloques de markdown
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
         code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    code = code.strip()

    # 2. Quitar el wrapper de función si el LLM lo escribió literal
    # Ejemplo: Python_CodeExecutor("""...""") o python(...)
    for wrapper in ["Python_CodeExecutor(", "python_executor(", "python("]:
        if code.startswith(wrapper) and code.endswith(")"):
            code = code[len(wrapper):-1].strip()
            # Quitar comillas triples o simples del inicio/fin del bloque interno
            for quote in ['"""', "'''", '"', "'"]:
                if code.startswith(quote) and code.endswith(quote):
                    code = code[len(quote):-len(quote)].strip()
                    break
            break

    code = code.strip()

    f_out = io.StringIO()
    # Ejecutamos en un scope vacío de python local
    with contextlib.redirect_stdout(f_out), contextlib.redirect_stderr(f_out):
        try:
            # Usando globals y locals genéricos para permitir imports y persistencia en un mismo script
            exec(code, {}, {})
        except Exception as e:
            traceback.print_exc(file=f_out)
    
    output = f_out.getvalue()
    if not output.strip():
        output = "La ejecución del código en Python fue exitosa y no devolvió errores ni salida en consola."
        
    return output

# Define la herramienta para LangChain
open_interpreter_tool = Tool(
    name="Python_CodeExecutor",
    func=execute_python_code,
    description="Útil cuando necesitas crear o ejecutar scripts en Python para resolver un problema, generar una gráfica, o procesar datos. DEBES ENVIAR EL CÓDIGO PYTHON DIRECTO. NO ENVÍES TEXTO EN LENGUAJE NATURAL."
)
