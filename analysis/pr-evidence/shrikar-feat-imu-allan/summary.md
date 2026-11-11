# IMU Allan deviation: 20261110-0306-static-bench-overnight

Session `20261110-0306-static-bench-overnight` (recorded at commit `7763667`), analysed at commit `7ed2c65-dirty`. Hardware: ['host', 'mpu6050']. Window from 1800 s to 18000 s of the session.

1620000 samples over 16200 s at 100.0 Hz; 1 intervals > 1.5x nominal, longest 0.018 s.

| Sensor | Axis | Noise density | Allan check (slope) | Sim model | Floor | at τ (s) | Floor reached | Static mean | Spectral peak (Hz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| accel | x | 214 ug/sqrt(Hz) | 227 (-0.49) | 400 | 119 ug (sim 37) | 4.02 | yes | -0.5642 m/s² | 1.64 |
| accel | y | 198 ug/sqrt(Hz) | 208 (-0.50) | 400 | 64.7 ug (sim 33.8) | 12.8 | yes | 2 m/s² | 6.81 |
| accel | z | 309 ug/sqrt(Hz) | 324 (-0.50) | 400 | 94.5 ug (sim 27.6) | 10.1 | yes | 8.842 m/s² | 4.59 |
| gyro | x | 0.00492 deg/s/sqrt(Hz) | 0.00549 (-0.50) | 0.005 | 5.54 deg/h (sim 5.47) | 20.2 | yes | -3.723 deg/s | 42.11 |
| gyro | y | 0.00534 deg/s/sqrt(Hz) | 0.00813 (-0.50) | 0.005 | 3.73 deg/h (sim 6.35) | 102 | yes | 0.8509 deg/s | 4.66 |
| gyro | z | 0.0049 deg/s/sqrt(Hz) | 0.00571 (-0.50) | 0.005 | 4.7 deg/h (sim 6.44) | 50.9 | yes | 1.002 deg/s | 6.81 |

Mean |accel| 9.0825 m/s² against g = 9.80665 (-7.4 %): scale and bias together; a single static pose cannot separate them.

Noise density is the median spectrum in 10-30 Hz, in the sim's convention (`pnt.sim.sensors`: sigma = N·sqrt(fs/2)), so it can replace the `ImuParams` value. *Allan check* is the same density from the curve's slope -1/2 stretch (its slope in brackets); a vibration (see the spectral peak) bends the curve and makes it disagree. *Floor reached: no* means the curve was still falling at the longest τ: the record is too short to see the bias instability.
