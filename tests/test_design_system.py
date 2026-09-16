"""Keep the supplied design portable without executing its demo application."""
import re
from tools.build_design_system import compile_css, TARGET, ROOT


def test_generated_stylesheet_is_current():
    assert TARGET.read_text(encoding="utf-8") == compile_css()


def test_local_stylesheet_resources_exist():
    urls = re.findall(r'url\([\"\']?([^\"\')]+)', compile_css())
    local = [url for url in urls if not url.startswith("data:")]
    assert local
    assert all((TARGET.parent / url).is_file() for url in local)


def test_reference_components_are_mapped_without_demo_runtime():
    css = compile_css()
    assert ':is(.zd-header,.app-header)' in css
    assert ':is(.zd-dock,.app-dock)' in css
    html = (TARGET.parent / "index.html").read_text(encoding="utf-8")
    assert '_ds_bundle' not in html
    assert 'design/reference' not in html


def test_motion_preferences_include_live_app_values():
    bridge = (TARGET.parent / "design-system-bridge.css").read_text(encoding="utf-8")
    for state in ('off', 'reduced'):
        assert f'[data-motion="{state}"]' in bridge
    assert 'prefers-reduced-motion: reduce' in bridge


def test_design_styles_load_after_legacy_styles():
    html = (TARGET.parent / "index.html").read_text(encoding="utf-8")
    assert html.index('./design-pass.css') < html.index('./design-system.css')
    assert html.index('./design-system.css') < html.index('./design-system-bridge.css')
