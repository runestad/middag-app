"""One-time metric conversion for new imports; never applied to saved edits."""
import re
from .import_validation import quantity

# Volume stays volume: a cup of flour is not a cup of water by weight.
UNITS = {
    'cup': ('dl', 2.4), 'cups': ('dl', 2.4),
    'us cup': ('dl', 2.4), 'metric cup': ('dl', 2.5),
    'tablespoon': ('ss', 1), 'tablespoons': ('ss', 1), 'tbsp': ('ss', 1),
    'teaspoon': ('ts', 1), 'teaspoons': ('ts', 1), 'tsp': ('ts', 1),
    'ounce': ('g', 28.3495), 'ounces': ('g', 28.3495), 'oz': ('g', 28.3495),
    'pound': ('g', 453.592), 'pounds': ('g', 453.592), 'lb': ('g', 453.592), 'lbs': ('g', 453.592),
    'fl oz': ('ml', 29.5735), 'fluid ounce': ('ml', 29.5735), 'fluid ounces': ('ml', 29.5735),
    'gram': ('g', 1), 'grams': ('g', 1), 'kilogram': ('kg', 1), 'kilograms': ('kg', 1),
    'milliliter': ('ml', 1), 'milliliters': ('ml', 1), 'litre': ('l', 1), 'liter': ('l', 1),
    'clove': ('fedd', 1), 'cloves': ('fedd', 1), 'piece': ('stk', 1), 'pieces': ('stk', 1),
    'can': ('boks', 1), 'cans': ('boks', 1), 'tin': ('boks', 1), 'tins': ('boks', 1),
    'package': ('pakke', 1), 'packet': ('pakke', 1), 'pinch': ('klype', 1),
    'handful': ('håndfull', 1), 'bunch': ('bunt', 1), 'sprig': ('kvist', 1),
}

def norwegian_amount(value):
    number = quantity(value)
    if number is None:
        return str(value or '').strip()
    return format(round(float(number), 3), 'g').replace('.', ',')


def metric_ingredient(ingredient):
    result = dict(ingredient)
    amount = str(result.get('amount') or '').strip()
    unit = str(result.get('unit') or '').lower().strip().rstrip('.')
    target, factor = UNITS.get(unit, (unit, 1))
    pieces = re.split(r'\s*[–-]\s*', amount)
    values = [quantity(piece) for piece in pieces]
    if amount and all(value is not None for value in values) and len(values) <= 2:
        result['amount'] = '–'.join(norwegian_amount(str(float(value) * factor)) for value in values)
        result['unit'] = target
    elif factor == 1:
        result['amount'], result['unit'] = amount, target
    # Never relabel an unconvertible compound amount with the wrong unit.
    return result
