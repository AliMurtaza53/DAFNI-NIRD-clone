"""Constants used in the network flow model"""

CONV_METER_TO_MILE = 0.000621371
CONV_MILE_TO_KM = 1.60934
CONV_KM_TO_MILE = 0.621371
PENCE_TO_POUND = 0.01
GBP_TO_USD = 1.27  # Exchange rate conversion factor

# Value of Time in USD per hour (converted from GBP at 1.27 GBP:USD)
VOT_POUND_PER_HOUR = {
    "car": 27.19,  # USD per hour (21.41 GBP * 1.27)
    "lgv": 21.42,  # USD per hour (16.87 GBP * 1.27)
    "ogv": 25.84,  # USD per hour (20.35 GBP * 1.27)
    "psv": 16.70,  # USD per hour (13.15 GBP * 1.27)
    "rail": 48.62,  # USD per hour (38.28 GBP * 1.27)
}

# Fuel consumption in litres per mile (converted from per km)
# Original units: litres per km. Convert by multiplying by CONV_KM_TO_MILE
FUEL_LITRE_PER_KM = {
    "car": {"a": 0.75232, "b": 0.05130, "c": 0.00057, "d": 0.000000372},  # per mile (adjusted)
    "lgv": {"a": 0.65074, "b": 0.09512, "c": -0.00301, "d": 0.000020},  # per mile (adjusted)
    "ogv": {"a": 6.73854, "b": 0.13573, "c": -0.00191, "d": 0.000014},  # per mile (adjusted)
    "psv": {"a": 5.41589, "b": 0.18347, "c": -0.00206, "d": 0.000015},  # per mile (adjusted)
}

# Non-fuel operating costs in cents USD per mile (converted from pence GBP per km)
# Original: pence per km, converted to cents USD per mile
NON_FUEL_PENCE_PER_KM = {
    "car": {"a": 8.74, "b": 239.77},  # cents USD per mile
    "lgv": {"a": 12.70, "b": 83.06},  # cents USD per mile
    "ogv": {"a": 17.41, "b": 680.18},  # cents USD per mile
    "psv": {"a": 53.67, "b": 1223.40},  # cents USD per mile
}
