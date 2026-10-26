"""无需 Qt 界面的批量扫描入口，供终端和智能体调用。"""
import argparse
import csv
from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys


EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
CSV_COLUMNS = ['源文件', '输出文件', '宽', '高', '字节', 'JPEG质量', '体积限制缩图', '状态', '说明']


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def create_parser():
    parser = Parser(
        description='本地批量扫描图片；带参数启动时不显示界面。',
        epilog='示例：%(prog)s -i "D:\\photo" -o "E:\\output" -s 90 -e 50',
        allow_abbrev=False,
        add_help=False,
    )
    parser._positionals.title = '位置参数'
    parser._optionals.title = '可选参数'
    parser.add_argument('-h', '--help', action='help', help='显示参数说明并退出')
    parser.add_argument('-i', '--input', nargs='+', action='append', metavar='PATH', help='输入图片或目录，可指定多个或重复使用 -i')
    parser.add_argument('-o', '--output', type=Path, metavar='DIR', help='输出目录，必填；同名文件自动编号')
    parser.add_argument('-s', '--scale', type=float, metavar='PERCENT', help='校正后宽高的缩放百分比，1～200，默认 100')
    parser.add_argument('-e', '--enhance', type=float, default=100, metavar='PERCENT', help='增强强度，0～100，默认 100；0 表示关闭增强')
    parser.add_argument('--black-white', action='store_true', help='启用黑白文字模式；彩色内容也会转黑白，建议导出 PNG')
    parser.add_argument('--black-threshold', type=int, default=180, metavar='N', help='灰度低于此值转黑，其余转白；1～255，默认 180，仅黑白模式生效')
    parser.add_argument('--stroke-radius', type=int, default=1, metavar='PIXELS', help='黑色笔画加粗半径，0～3 像素，默认 1；0 不加粗，仅黑白模式生效')
    parser.add_argument('-r', '--recursive', action='store_true', help='递归扫描输入目录的子目录')
    parser.add_argument('--width', type=int, metavar='PIXELS', help='输出最大宽度，保持比例，不能与 -s 同用')
    parser.add_argument('--height', type=int, metavar='PIXELS', help='输出最大高度，保持比例，不能与 -s 同用')
    parser.add_argument('--format', type=str.upper, choices=['JPEG', 'JPG', 'PNG'], default='JPEG', help='输出格式，默认 JPEG')
    parser.add_argument('--quality', type=int, default=95, metavar='N', help='JPEG 质量，60～100，默认 95')
    parser.add_argument('--max-mb', type=float, metavar='MB', help='单张文件大小上限，0.01～1000 MB；默认不限制')
    parser.add_argument('--no-crop', action='store_true', help='关闭纸张检测和透视裁剪')
    parser.add_argument('--no-fill-frame', action='store_true', help='关闭纸边精修')
    parser.add_argument('--dewarp', action='store_true', help='启用曲面展平，默认关闭')
    parser.add_argument('--rotate', type=int, choices=[0, 90, 180, 270], default=0, help='处理前顺时针旋转角度，默认 0')
    parser.add_argument('--json', action='store_true', help='stdout 仅输出一份 JSON 结果，进度和模型日志写入 stderr')
    parser.add_argument('--quiet', action='store_true', help='隐藏逐张进度；错误、汇总和模型诊断仍保留')
    parser.add_argument('--no-csv', action='store_true', help='不生成 CSV 处理记录')
    return parser


def validate_options(args):
    if not args.input or args.output is None:
        raise ValueError('必须使用 -i 指定输入，并使用 -o 指定输出目录；--help 可查看说明')
    if not math.isfinite(args.enhance) or not 0 <= args.enhance <= 100:
        raise ValueError('增强强度必须在 0 到 100 之间')
    if not 1 <= args.black_threshold <= 255:
        raise ValueError('黑白阈值必须在 1 到 255 之间')
    if not 0 <= args.stroke_radius <= 3:
        raise ValueError('笔画加粗半径必须在 0 到 3 之间')
    if args.scale is not None and (not math.isfinite(args.scale) or not 1 <= args.scale <= 200):
        raise ValueError('缩放比例必须在 1 到 200 之间')
    custom = args.width is not None or args.height is not None
    if custom and args.scale is not None:
        raise ValueError('--width / --height 不能与 -s / --scale 同时使用')
    # 参数和目录先校验，再加载模型或创建结果文件。
    from .exporting import ExportOptions
    mode = 'original'
    if custom:
        mode = 'custom'
    elif args.scale is not None:
        mode = 'percent'
    options = ExportOptions(
        mode=mode,
        percent=args.scale if args.scale is not None else 100,
        width=args.width or 0,
        height=args.height or 0,
        format='JPEG' if args.format == 'JPG' else args.format,
        quality=args.quality,
        max_mb=args.max_mb,
    )
    options.validate()
    return options


def collect_inputs(groups, output: Path, recursive: bool):
    """先固定输入列表，跳过隐藏目录、重复文件及输出目录，避免扫描自身结果。"""
    inputs = []
    seen = set()

    def add(path):
        path = path.resolve()
        if path not in seen and output not in path.parents and path.suffix.lower() in EXTENSIONS:
            seen.add(path)
            inputs.append(path)

    def walk_error(error):
        raise error

    for value in (value for group in groups for value in group):
        source = Path(value).expanduser().resolve()
        if source.is_file():
            if source.suffix.lower() not in EXTENSIONS:
                raise ValueError(f'不支持的输入格式：{source}')
            if output in source.parents:
                raise ValueError(f'输入文件不能位于输出目录内：{source}')
            add(source)
        elif source.is_dir():
            if source == output or output in source.parents:
                raise ValueError(f'输入目录不能等于输出目录或位于输出目录内：{source}')
            for root, directories, files in os.walk(source, onerror=walk_error, followlinks=False):
                directory = Path(root)
                directories[:] = sorted(
                    name for name in directories
                    if not name.startswith('.') and (directory / name).resolve() != output
                ) if recursive else []
                for name in sorted(files):
                    path = directory / name
                    if not name.startswith('.') and path.is_file():
                        add(path)
        else:
            raise ValueError(f'输入路径不存在或不是普通文件/目录：{source}')
    if not inputs:
        raise ValueError('没有找到支持的图片；如需处理子目录，请添加 --recursive')
    return inputs


def write_csv(output: Path, files):
    record = output / f'处理记录_{datetime.now():%Y%m%d_%H%M%S_%f}.csv'
    with record.open('x', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for item in files:
            row = {'源文件': item['input'], '状态': '完成' if item['status'] == 'success' else '失败', '说明': item.get('error') or item.get('warning', '')}
            if item['status'] == 'success':
                row.update({'输出文件': item['output'], '宽': item['width'], '高': item['height'], '字节': item['bytes'], 'JPEG质量': item['quality'] or '', '体积限制缩图': '是' if item['resized_for_limit'] else '否'})
            writer.writerow(row)
    return str(record)


def run_batch(args, report, export):
    from .engine import ScanOptions, Scanner
    from .exporting import encode_image, save_unique

    output = args.output.expanduser().resolve()
    paths = collect_inputs(args.input, output, args.recursive)
    if output.exists() and not output.is_dir():
        raise ValueError(f'输出路径不是目录：{output}')
    report['total'] = len(paths)
    output.mkdir(parents=True, exist_ok=True)
    scan = ScanOptions(auto_crop=not args.no_crop, enhance=args.enhance > 0,
                       strength=args.enhance / 100, dewarp=args.dewarp, fill_frame=not args.no_fill_frame,
                       black_white=args.black_white, black_threshold=args.black_threshold, stroke_radius=args.stroke_radius)
    scanner = Scanner()
    try:
        for index, path in enumerate(paths, 1):
            if not args.quiet:
                print(f'正在处理 {index} / {len(paths)} · {path.name}', file=sys.stderr, flush=True)
            item = {'input': str(path), 'status': 'failed'}
            try:
                result = scanner.process(path, scan, rotation=args.rotate)
                encoded = encode_image(result.image, export)
                destination = save_unique(encoded, output, path.stem, export.format)
                item.update(status='success', output=str(destination), width=encoded.width, height=encoded.height,
                            bytes=len(encoded.data), quality=encoded.quality, resized_for_limit=encoded.resized_for_limit,
                            warning=result.warning, seconds=round(result.seconds, 3))
                report['succeeded'] += 1
                if result.warning and not args.quiet:
                    print(f'提示：{path.name}：{result.warning}', file=sys.stderr)
            except Exception as error:
                item['error'] = str(error) or type(error).__name__
                report['failed'] += 1
                print(f'处理失败：{path}：{item["error"]}', file=sys.stderr)
            report['files'].append(item)
    except KeyboardInterrupt:
        report.update(status='cancelled', exit_code=130, error='用户中断处理，已完成的文件保留')
    else:
        report['exit_code'] = 1 if report['failed'] else 0
        report['status'] = 'success'
        if report['failed']:
            report['status'] = 'partial_failure' if report['succeeded'] else 'failed'
    if report['files'] and not args.no_csv:
        try:
            report['record'] = write_csv(output, report['files'])
        except OSError as error:
            report['error'] = f'无法保存 CSV 处理记录：{error}'
            if report['exit_code'] != 130:
                report.update(status='error', exit_code=1)
            print(report['error'], file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # 统一 UTF-8，智能体无需依赖 Windows 的当前代码页。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    json_mode = '--json' in argv and not any(flag in argv for flag in ('-h', '--help'))
    result_stream = sys.stdout
    if json_mode:
        # CLI 独立进程保留原 stdout 专供结果使用。将 fd 1 持续导向 stderr，
        # 同时隔离 Python print、MNN 原生日志以及解释器退出时的缓冲输出。
        sys.stdout.flush()
        result_stream = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8')
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        if sys.platform == 'win32':
            import ctypes
            import msvcrt
            # 同步 Win32 句柄，兼容直接调用 GetStdHandle 的原生依赖。
            set_handle = ctypes.windll.kernel32.SetStdHandle
            set_handle.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
            set_handle.restype = ctypes.c_int
            if not set_handle(0xFFFFFFF5, msvcrt.get_osfhandle(sys.stderr.fileno())):
                raise ctypes.WinError()
        sys.stdout = sys.stderr
    parser = create_parser()
    report = {'schema_version': 1, 'status': 'error', 'exit_code': 2, 'total': 0,
              'succeeded': 0, 'failed': 0, 'files': [], 'record': None, 'error': None}
    try:
        args = parser.parse_args(argv)
        export = validate_options(args)
        run_batch(args, report, export)
    except ValueError as error:
        report['error'] = str(error)
        print(f'参数或输入错误：{error}', file=sys.stderr)
    except KeyboardInterrupt:
        report.update(status='cancelled', exit_code=130, error='用户中断处理')
    except Exception as error:
        report.update(status='error', exit_code=1, error=str(error) or type(error).__name__)
        print(f'执行失败：{report["error"]}', file=sys.stderr)
    if json_mode:
        try:
            print(json.dumps(report, ensure_ascii=False, allow_nan=False), file=result_stream, flush=True)
        finally:
            result_stream.close()
    else:
        print(f'处理结束：成功 {report["succeeded"]}，失败 {report["failed"]}，共 {report["total"]} 张；退出码 {report["exit_code"]}', file=sys.stderr)
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
