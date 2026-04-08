
def detect_leak(volumes):
    leaks = []
    for i in range(1, len(volumes)):
        delta = volumes[i] - volumes[i-1]
        if delta < -0.2:
            leaks.append((i, delta))
    return leaks
