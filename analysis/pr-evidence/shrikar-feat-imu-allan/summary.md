# IMU Allan deviation: 20261110-0306-overnight-partial

Session `20261110-0306-overnight-partial` (recorded at commit `25ce8ba`), analysed at commit `1ba349e`. Hardware: ['host', 'mpu6050']. First 0 s dropped.

56550 samples over 565 s at 100.0 Hz; 0 intervals > 1.5x nominal, longest 0.013 s.

| Sensor | Axis | Noise density | Allan check (slope) | Sim model | Floor | at τ (s) | Floor reached | Static mean | Spectral peak (Hz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| accel | x | 291 ug/sqrt(Hz) | 373 (-0.47) | 400 | 145 ug (sim 52.2) | 4.33 | yes | -0.08993 m/s² | 4.27 |
| accel | y | 207 ug/sqrt(Hz) | 299 (-0.50) | 400 | 105 ug (sim 50.1) | 8.73 | yes | 1.896 m/s² | 5.54 |
| accel | z | 357 ug/sqrt(Hz) | 362 (-0.50) | 400 | 68.3 ug (sim 52.9) | 17.6 | yes | 8.86 m/s² | 4.59 |
| gyro | x | 0.026 deg/s/sqrt(Hz) | 0.0363 (-0.65) | 0.005 | 7.7 deg/h (sim 6.78) | 56.6 | no | -3.739 deg/s | 5.54 |
| gyro | y | 0.0521 deg/s/sqrt(Hz) | 0.173 (-0.39) | 0.005 | 5.33 deg/h (sim 5.84) | 56.6 | no | 0.8524 deg/s | 4.59 |
| gyro | z | 0.0143 deg/s/sqrt(Hz) | 0.0645 (-0.38) | 0.005 | 4.61 deg/h (sim 7.14) | 56.6 | no | 1.005 deg/s | 5.54 |

Mean |accel| 9.0607 m/s² against g = 9.80665 (-7.6 %): scale and bias together; a single static pose cannot separate them.

Noise density is the median spectrum in 10-30 Hz, in the sim's convention (`pnt.sim.sensors`: sigma = N·sqrt(fs/2)), so it can replace the `ImuParams` value. *Allan check* is the same density from the curve's slope -1/2 stretch (its slope in brackets); a vibration (see the spectral peak) bends the curve and makes it disagree. *Floor reached: no* means the curve was still falling at the longest τ: the record is too short to see the bias instability.
