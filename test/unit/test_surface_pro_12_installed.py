from pathlib import Path
import sys, tempfile, unittest
import types
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'configs/airootfs/usr/share/omarchy-iso'))
sys.modules.setdefault('orchestrator.archinstall_adapter', types.ModuleType('orchestrator.archinstall_adapter'))
from orchestrator.hardware import detect_hardware_profile
from orchestrator import phases_impl

class SurfaceHardwareTest(unittest.TestCase):
    def fixture(self, values):
        d=tempfile.TemporaryDirectory(); root=Path(d.name)
        for k,v in values.items(): (root/k).write_text(v)
        return d,root
    def test_exact_profile_and_optional_board(self):
        values={'sys_vendor':'Microsoft Corporation','product_family':'Surface','product_name':'Surface Pro 12in 1st Ed with Snapdragon','product_sku':'Surface_Pro_12in_1st_Ed_with_Snapdragon_2110'}
        d,r=self.fixture(values); self.addCleanup(d.cleanup)
        self.assertEqual(detect_hardware_profile(r),'surface-pro-12')
    def test_exact_board_value_is_accepted(self):
        values={'sys_vendor':'Microsoft Corporation','product_family':'Surface','product_name':'Surface Pro 12in 1st Ed with Snapdragon','product_sku':'Surface_Pro_12in_1st_Ed_with_Snapdragon_2110','board_vendor':'Microsoft Corporation','board_name':'Surface Pro 12in 1st Ed with Snapdragon'}
        d,r=self.fixture(values); self.addCleanup(d.cleanup)
        self.assertEqual(detect_hardware_profile(r),'surface-pro-12')
    def test_other_surface_incomplete_and_forged_board_fail(self):
        base={'sys_vendor':'Microsoft Corporation','product_family':'Surface','product_name':'Surface Pro 12in 1st Ed with Snapdragon','product_sku':'wrong'}
        d,r=self.fixture(base); self.addCleanup(d.cleanup); self.assertIsNone(detect_hardware_profile(r))
        base['product_sku']='Surface_Pro_12in_1st_Ed_with_Snapdragon_2110'; base.update({'board_vendor':'evil','board_name':'fake'})
        d,r=self.fixture(base); self.addCleanup(d.cleanup); self.assertIsNone(detect_hardware_profile(r))

    def test_surface_defaults_repeat_args_after_high_priority_assignment(self):
        rendered = 'KERNEL_CMDLINE[default]+=\"initramfs_async=0 clk_ignore_unused pd_ignore_unused arm64.nopauth\"'
        self.assertIn('KERNEL_CMDLINE[default]+=', rendered)
        self.assertEqual(
            phases_impl._limine_kernel_cmdline('KERNEL_CMDLINE[default]="root=UUID=x"\n' + rendered),
            'initramfs_async=0 clk_ignore_unused pd_ignore_unused arm64.nopauth',
        )

    def test_surface_limine_defaults_are_rendered_from_settings_package_template(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            templates = target / 'usr/share/omarchy/default/limine'
            templates.mkdir(parents=True)
            (templates / 'default.conf').write_text(
                'ESP_PATH="/boot"\nKERNEL_CMDLINE[default]+="@@CMDLINE@@"\n'
            )
            (templates / 'limine.conf').write_text('Omarchy\n')
            ctx = types.SimpleNamespace(
                target=target,
                omarchy_path=Path('/not-used'),
                omarchy_install={'hardware_profile': 'surface-pro-12'},
            )
            with mock.patch.object(phases_impl.arch, 'has_uefi', return_value=True, create=True):
                phases_impl._write_limine_defaults(ctx, 'root=UUID=root rw', esp_mount='/boot')
            rendered = (target / 'etc/default/limine').read_text()
            self.assertIn('KERNEL_CMDLINE[default]+="root=UUID=root rw"', rendered)
            self.assertIn('MKINITCPIO_FALLBACK=yes', rendered)
            self.assertIn('ENABLE_UKI=yes', rendered)
            self.assertIn('CUSTOM_UKI_NAME=omarchy', rendered)
            self.assertIn('arm64.nopauth', rendered)
            self.assertEqual((target / 'boot/limine.conf').read_text(), 'Omarchy\n')
