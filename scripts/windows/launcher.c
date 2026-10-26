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
static int cli_mode = 0;

typedef int (__cdecl *PythonMain)(int, wchar_t **);

static int error_message(const wchar_t *message) {
    if (cli_mode) {
        char text[4096];
        int size = WideCharToMultiByte(CP_UTF8, 0, message, -1, text, sizeof(text), NULL, NULL);
        DWORD written;
        HANDLE error = GetStdHandle(STD_ERROR_HANDLE);
        if (size > 0 && error && error != INVALID_HANDLE_VALUE) {
            WriteFile(error, text, size - 1, &written, NULL);
            WriteFile(error, "\r\n", 2, &written, NULL);
        }
    } else {
        MessageBoxW(NULL, message, L"纸页扫描", MB_OK | MB_ICONERROR);
    }
    return 1;
}

static int valid_handle(HANDLE handle) {
    return handle && handle != INVALID_HANDLE_VALUE && GetFileType(handle) != FILE_TYPE_UNKNOWN;
}

static void prepare_console(void) {
    /* 保留调用方传入的管道或文件；只补齐 GUI 进程缺失的控制台句柄。 */
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    HANDLE error = GetStdHandle(STD_ERROR_HANDLE);
    if (!valid_handle(output) || !valid_handle(error)) {
        AttachConsole(ATTACH_PARENT_PROCESS);
        if (valid_handle(output)) SetStdHandle(STD_OUTPUT_HANDLE, output);
        if (valid_handle(error)) SetStdHandle(STD_ERROR_HANDLE, error);
    }
    SetConsoleOutputCP(CP_UTF8);
}

static int join_path(wchar_t *destination, const wchar_t *suffix) {
    if (wcslen(root) + wcslen(suffix) + 1 >= PATH_CAPACITY) return 0;
    wcscpy(destination, root);
    wcscat(destination, suffix);
    return 1;
}

static int launch(void) {
    int count = 0;
    wchar_t **arguments = CommandLineToArgvW(GetCommandLineW(), &count);
#ifdef CONSOLE_LAUNCHER
    cli_mode = 1;
#else
    cli_mode = arguments && count > 1 && !(count == 4 && wcscmp(arguments[1], L"--self-test") == 0);
#endif
    if (cli_mode) prepare_console();
    if (!arguments || count < 1) return error_message(L"无法读取启动参数。");
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
    wchar_t **python_arguments = (wchar_t **)LocalAlloc(LPTR, sizeof(wchar_t *) * (count + 3));
    if (!python_arguments) { LocalFree(arguments); return error_message(L"内存不足，无法启动。"); }
    python_arguments[0] = arguments[0];
    python_arguments[1] = script;
    for (int index = 1; index < count; ++index) python_arguments[index + 1] = arguments[index];
    int python_count = count + 1;
#ifdef CONSOLE_LAUNCHER
    /* 控制台入口不带参数时显示帮助，避免意外启动界面。 */
    if (count == 1) python_arguments[python_count++] = L"--help";
#endif
    int result = run_python(python_count, python_arguments);
    LocalFree(python_arguments);
    LocalFree(arguments);
    return result;
}

#ifdef CONSOLE_LAUNCHER
int wmain(int argc, wchar_t **argv) {
    (void)argc; (void)argv;
    return launch();
}
#else
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
    return launch();
}
#endif
