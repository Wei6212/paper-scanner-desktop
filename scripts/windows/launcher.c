/* 在带 UTF-8 清单的同一进程中载入 Python，兼容模型的中文文件路径。 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

#define PATH_CAPACITY 32768
static wchar_t root[PATH_CAPACITY];
static wchar_t runtime[PATH_CAPACITY];
static wchar_t library[PATH_CAPACITY];
static wchar_t script[PATH_CAPACITY];

typedef int (__cdecl *PythonMain)(int, wchar_t **);

static int error_message(const wchar_t *message) {
    MessageBoxW(NULL, message, L"纸页扫描", MB_OK | MB_ICONERROR);
    return 1;
}

static int join_path(wchar_t *destination, const wchar_t *suffix) {
    if (wcslen(root) + wcslen(suffix) + 1 >= PATH_CAPACITY) return 0;
    wcscpy(destination, root);
    wcscat(destination, suffix);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
    DWORD size = GetModuleFileNameW(NULL, root, PATH_CAPACITY);
    if (!size || size >= PATH_CAPACITY) return error_message(L"应用所在路径过长，请解压到较短的目录后重试。");
    wchar_t *separator = wcsrchr(root, L'\\');
    if (!separator) return error_message(L"无法确定应用目录。");
    *separator = L'\0';
    if (!join_path(runtime, L"\\runtime") || !join_path(library, L"\\runtime\\python312.dll") || !join_path(script, L"\\app\\launch.py"))
        return error_message(L"应用所在路径过长，请解压到较短的目录后重试。");
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES || GetFileAttributesW(library) == INVALID_FILE_ATTRIBUTES)
        return error_message(L"运行文件不完整。请先解压整个压缩包，再双击纸页扫描.exe，不能只复制 exe。");
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    AddDllDirectory(runtime);
    SetEnvironmentVariableW(L"PYTHONHOME", runtime);
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    HMODULE python = LoadLibraryExW(library, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!python) return error_message(L"无法加载应用内的运行时。请确认使用 Windows 10/11 64 位，并完整解压所有文件。");
    PythonMain run_python = (PythonMain)GetProcAddress(python, "Py_Main");
    if (!run_python) return error_message(L"运行时入口缺失，请重新解压完整压缩包。");
    int count = 0;
    wchar_t **arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!arguments || count < 1) return error_message(L"无法读取启动参数。");
    wchar_t **python_arguments = (wchar_t **)LocalAlloc(LPTR, sizeof(wchar_t *) * (count + 2));
    if (!python_arguments) { LocalFree(arguments); return error_message(L"内存不足，无法启动。"); }
    python_arguments[0] = arguments[0];
    python_arguments[1] = script;
    for (int index = 1; index < count; ++index) python_arguments[index + 1] = arguments[index];
    int result = run_python(count + 1, python_arguments);
    LocalFree(python_arguments);
    LocalFree(arguments);
    return result;
}
