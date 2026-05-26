import argparse

from .variants import PRODUCT_DEFINITIONS, detect_hardware_variant, get_product_definition, normalize_variant_key


def _selected_variant(variant):
    if variant != "auto":
        return normalize_variant_key(variant), "selected"
    detected = detect_hardware_variant()
    return detected["variant"], detected["source"]


def _plan_lines(variant):
    variant_key, source = _selected_variant(variant)
    product = get_product_definition(variant_key)
    overlays = product.get("dt_overlays", []) if product else []
    config_txt = product.get("config_txt", {}) if product else {}

    lines = [
        "System setup plan",
        f"Variant: {product['name']} ({variant_key}, {source})",
        "No changes made.",
        "",
        "Privileged changes:",
    ]
    for overlay in overlays:
        lines.append(f"- Install overlay: /boot/firmware/overlays/{overlay}")
    if "oled" in product.get("modules", []):
        lines.append("- Write module config: /etc/modules-load.d/pironman5.conf (i2c-dev)")
    elif config_txt:
        lines.append("- Write module config: /etc/modules-load.d/pironman5.conf when I2C devices are enabled")
    for name, value in config_txt.items():
        lines.append(f"- Set boot config: {name}={value}")
    lines.extend([
        "- Install udev/device access rules for i2c, spi, gpio, and pwm devices",
        "- Create or update the pironman5 service user and systemd service",
    ])
    return lines


def build_parser():
    parser = argparse.ArgumentParser(prog="pironman5 system", description="Manage Pironman 5 system integration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    variant_choices = ["auto", *sorted(PRODUCT_DEFINITIONS)]
    plan = subparsers.add_parser("plan", help="Show privileged setup actions without changing the system")
    plan.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        print("\n".join(_plan_lines(args.variant)))
