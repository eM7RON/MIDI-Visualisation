import json

def get_spectrum(x):
    with open('spectrums.json', 'r') as f:
        spectrum = json.load(f)
    return spectrum[x]