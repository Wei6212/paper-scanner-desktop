"""验证独立进程调用、结果协议、批量容错及无界面运行。"""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from paper_scanner.cli import collect_inputs, create_parser, run_batch, validate_options


ROOT = Path(__file__).resolve().parents[1]


def invoke(*arguments, code=None):
    command = [sys.executable, '-c', code] if code else [sys.executable, str(ROOT / 'main.py')]
    return subprocess.run(command + list(map(str, arguments)), cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', timeout=120,
                          env={**os.environ, 'QT_QPA_PLATFORM': '不存在的测试平台'})


def invoke_json(*arguments, code=None):
    result = invoke(*arguments, '--json', code=code)
    report = json.loads(result.stdout)
    assert result.returncode == report['exit_code'], result.stderr
    assert report['schema_version'] == 1
    return result, report


@pytest.fixture
def source(tmp_path):
    path = tmp_path / '输入 图片.png'
    Image.new('RGB', (120, 80), '#c84126').save(path)
    return path


def test_help_does_not_import_gui_or_models():
    code = '''
import builtins, runpy, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('PySide6', 'MNN', 'cv2')):
        raise AssertionError('帮助命令不应加载界面或模型')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = ['main.py', '--help']
runpy.run_path('main.py', run_name='__main__')
'''
    result = invoke(code=code)
    assert result.returncode == 0, result.stderr
    assert '--input' in result.stdout
    assert '--json' in result.stdout


def test_no_arguments_still_dispatches_to_gui():
    code = '''
import runpy, sys, types
ui = types.ModuleType('paper_scanner.ui')
ui.main = lambda: 7
sys.modules['paper_scanner.ui'] = ui
sys.argv = ['main.py']
runpy.run_path('main.py', run_name='__main__')
'''
    assert invoke(code=code).returncode == 7


@pytest.mark.parametrize('extra', [
    ['-s', '0'], ['-s', 'nan'], ['-s', '201'], ['-e', '-1'], ['-e', 'inf'],
    ['--quality', '59'], ['--max-mb', 'nan'], ['--max-mb', '0.001'],
    ['--width', '-2'], ['--width', '0'], ['--width', '30001'],
    ['--width', '40', '-s', '50'], ['--rotate', '45'], ['--unknown'],
])
def test_invalid_parameters_fail_before_writing(source, tmp_path, extra):
    output = tmp_path / '结果'
    _, report = invoke_json('-i', source, '-o', output, *extra)
    assert report['exit_code'] == 2
    assert report['error']
    assert not output.exists()


def test_missing_input_and_empty_directory(tmp_path):
    for arguments in [[], ['-i', tmp_path / '不存在', '-o', tmp_path / '结果'],
                      ['-i', tmp_path, '-o', tmp_path / '结果']]:
        _, report = invoke_json(*arguments)
        assert report['exit_code'] == 2
        assert report['total'] == 0


@pytest.mark.parametrize('options,size,format_name', [
    (['-s', '90'], (108, 72), 'JPEG'),
    (['--width', '60', '--height', '30', '--format', 'png'], (45, 30), 'PNG'),
    (['--rotate', '90', '--height', '60'], (40, 60), 'JPEG'),
])
def test_headless_export_parameters_and_csv(source, tmp_path, options, size, format_name):
    original = source.read_bytes()
    result, report = invoke_json('-i', source, '-o', tmp_path / '输出 图片', '--no-crop', '-e', '0', *options)
    assert report['status'] == 'success', result.stderr
    assert report['succeeded'] == report['total'] == 1
    item = report['files'][0]
    with Image.open(item['output']) as image:
        assert image.size == size
        assert image.format == format_name
    assert item['bytes'] == Path(item['output']).stat().st_size
    with open(report['record'], encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]['状态'] == '完成'
    assert rows[0]['输出文件'] == item['output']
    assert source.read_bytes() == original


def test_recursive_deduplication_output_exclusion_and_existing_files(tmp_path):
    source = tmp_path / '输入'
    nested = source / '子目录'
    output = nested / '输出'
    output.mkdir(parents=True)
    Image.new('RGB', (30, 20), 'red').save(source / '同名.png')
    Image.new('RGB', (30, 20), 'blue').save(nested / '同名.png')
    Image.new('RGB', (30, 20)).save(output / '同名_扫描.jpg')
    original = (output / '同名_扫描.jpg').read_bytes()
    (source / '.隐藏').mkdir()
    Image.new('RGB', (30, 20)).save(source / '.隐藏/不处理.png')
    arguments = ['-i', source, source / '同名.png', '-i', nested, '-o', output, '-r', '--no-crop', '-e', '0', '--no-csv']
    _, report = invoke_json(*arguments)
    assert report['total'] == report['succeeded'] == 2
    assert {Path(item['output']).name for item in report['files']} == {'同名_扫描_2.jpg', '同名_扫描_3.jpg'}
    assert (output / '同名_扫描.jpg').read_bytes() == original
    assert report['record'] is None


def test_nonrecursive_and_same_directory_rejected(tmp_path, source):
    nested = tmp_path / '子目录'
    nested.mkdir()
    Image.new('RGB', (20, 20)).save(nested / '子图.png')
    assert collect_inputs([[str(tmp_path)]], tmp_path / '输出', False) == [source]
    _, report = invoke_json('-i', tmp_path, '-o', tmp_path)
    assert report['exit_code'] == 2
    _, report = invoke_json('-i', source, '-o', tmp_path)
    assert report['exit_code'] == 2


def test_corrupt_image_continues_and_returns_failure(source, tmp_path):
    damaged = tmp_path / '损坏.jpg'
    damaged.write_bytes(b'not-an-image')
    _, report = invoke_json('-i', damaged, source, '-o', tmp_path / '输出', '--no-crop', '-e', '0', '--quiet')
    assert report['status'] == 'partial_failure'
    assert report['exit_code'] == 1
    assert report['succeeded'] == report['failed'] == 1
    assert report['files'][0]['error']
    assert Path(report['files'][1]['output']).is_file()
    _, failed = invoke_json('-i', damaged, '-o', tmp_path / '全失败', '--no-crop', '-e', '0')
    assert failed['status'] == 'failed'
    assert failed['exit_code'] == 1


def test_native_and_exit_logs_do_not_pollute_json(source, tmp_path):
    code = '''
import atexit, os
from paper_scanner.engine import Scanner
original = Scanner.process
def process(self, *args, **kwargs):
    print('模拟 Python 模型诊断', flush=True)
    os.write(1, b'native-model-log\\n')
    return original(self, *args, **kwargs)
Scanner.process = process
atexit.register(lambda: os.write(1, b'native-shutdown-log\\n'))
from paper_scanner.cli import main
raise SystemExit(main())
'''
    result, report = invoke_json('-i', source, '-o', tmp_path / '输出', '--no-crop', '-e', '0', code=code)
    assert report['status'] == 'success'
    assert 'native-model-log' in result.stderr
    assert 'native-shutdown-log' in result.stderr
    assert '模拟 Python 模型诊断' in result.stderr


def test_real_models_emit_clean_json_and_respect_file_limit(tmp_path):
    result, report = invoke_json('-i', ROOT / 'samples/手绘文档原图.jpg', '-o', tmp_path / '模型结果',
                                 '-s', '50', '-e', '50', '--dewarp', '--max-mb', '0.05')
    assert report['status'] == 'success', result.stderr
    assert report['files'][0]['bytes'] <= 50_000
    assert report['files'][0]['width'] > 100


def test_interrupt_preserves_completed_results_and_writes_csv(source, tmp_path, monkeypatch):
    from paper_scanner.engine import Scanner
    original = Scanner.process
    calls = 0

    def process(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        return original(self, *args, **kwargs)

    second = tmp_path / '第二张.png'
    Image.new('RGB', (20, 20)).save(second)
    args = create_parser().parse_args(['-i', str(source), str(second), '-o', str(tmp_path / '输出'), '--no-crop', '-e', '0'])
    report = {'files': [], 'succeeded': 0, 'failed': 0}
    monkeypatch.setattr(Scanner, 'process', process)
    run_batch(args, report, validate_options(args))
    assert report['exit_code'] == 130
    assert report['succeeded'] == 1
    assert Path(report['files'][0]['output']).is_file()
    assert Path(report['record']).is_file()


def test_interrupted_save_cleans_reserved_file_and_temporary(source, tmp_path, monkeypatch):
    from paper_scanner.exporting import EncodedImage, save_unique

    def interrupt(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(os, 'replace', interrupt)
    output = tmp_path / '输出'
    with pytest.raises(KeyboardInterrupt):
        save_unique(EncodedImage(b'encoded', 1, 1, 95, False), output, source.stem, 'JPEG')
    assert not list(output.iterdir())


def test_record_failure_is_not_reported_as_batch_success(source, tmp_path, monkeypatch):
    def fail_record(*args):
        raise OSError('记录目录不可写')

    monkeypatch.setattr('paper_scanner.cli.write_csv', fail_record)
    args = create_parser().parse_args(['-i', str(source), '-o', str(tmp_path / '输出'), '--no-crop', '-e', '0'])
    report = {'files': [], 'succeeded': 0, 'failed': 0, 'record': None}
    run_batch(args, report, validate_options(args))
    assert report['exit_code'] == 1
    assert report['succeeded'] == 1
    assert report['record'] is None
    assert 'CSV' in report['error']


def test_cli_processing_does_not_load_qt(source, tmp_path):
    code = '''
import builtins, runpy, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith('PySide6'):
        raise AssertionError('命令行处理不应加载 Qt')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv[0] = 'main.py'
runpy.run_path('main.py', run_name='__main__')
'''
    _, report = invoke_json('-i', source, '-o', tmp_path / '输出', '--no-crop', '-e', '0', code=code)
    assert report['status'] == 'success'
