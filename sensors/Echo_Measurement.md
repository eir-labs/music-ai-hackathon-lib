# Measuring a space by listening to it

Play a sweep at somewhere, record it, and get back the distances to everything
that reflected it, plus a number saying how much to trust them.

The confidence is the point. It starts at zero, climbs as repeated captures
agree, and stays low when the air will not sit still. That gives you a control
signal with an arc already in it, earned from the measurement rather than drawn
on afterwards. Nothing is trained and nothing needs to be.

## The short version

```
kitlib sweep --seconds 10 --out sweep.wav
```

Play that at the space through a loudspeaker and record the result. Repeat it
several times without moving anything. Then:

```
kitlib echo capture1.wav capture2.wav capture3.wav --celsius 4
```

```
3 captures at 4C, sound travelling 333.7 m/s
     18.01 m  +/- 0.05  seen 3/3  ######
     44.00 m  +/- 0.06  seen 3/3  ######
     97.01 m  +/- 0.02  seen 3/3  ##############

confidence 0.362
```

Add `--send` and the confidence and the distances land on the bus, where
anything can drive a parameter from them.

```
kitlib echo capture*.wav --celsius 4 --send --name lake
```

```
/sensor/lake_confidence <0..1>
/sensor/lake            <metres...>
```

## Pass the temperature

Sound travels at 343 m/s in a warm room and 334 m/s at four degrees. Leave it
at the default and every distance is about three percent long, which is three
metres out at a hundred. Measure the air and pass `--celsius`. It is the only
number here that changes the answer.

## Why repeats, not one long sweep

A sweep only averages correctly while the medium holds still. A car cabin holds
still. A lake does not: wind and temperature gradients shift arrival times over
tens of seconds, which smears the result in a way that looks like a worse
measurement rather than a moving one.

So fire several shorter sweeps instead of one long one. Ten seconds is a fair
compromise, five if it is windy. The disagreement between them is not waste, it
is the confidence signal.

## What the confidence actually is

Two things, multiplied:

- **How often a surface turned up.** Found in every capture beats found in two.
  A peak that will not reappear is usually weather rather than rock.
- **How closely the captures agree about where it is,** as the standard error of
  the estimated distance, against the resolution you say you care about.

Because it is a standard error, it shrinks with the square root of the number
of captures even when the scatter itself does not improve. More evidence always
helps, and evidence that disagrees never pretends to.

Two captures agreeing exactly are not treated as ten agreeing exactly. The
small-sample correction is applied, so a single confirmation cannot claim
certainty. That is why the first capture reports nothing at all: one
measurement corroborates nothing.

## Source and microphone placement

Put them together. Co-located, an echo delay is simply twice the distance over
the speed of sound, which is what the printed metres assume.

Separate them and each delay no longer describes a circle around one point but
an ellipse with the speaker and microphone at its foci. The numbers become half
the total path rather than a distance, and resolving actual positions needs the
baseline measured and a solver this does not have.

A loudspeaker is also directional at high frequency in a way a measurement
sphere is not, so where you aim it decides which part of the shoreline you
recover rather than how well.

## Several positions

One position gives distances but no directions: a reflector could be anywhere
on a circle. Two positions intersect to two candidate points. Three resolve it.

Nothing needs synchronising between them. Every delay is measured from that
recorder's own direct arrival, so each position is its own time reference. Give
each one its own name on the bus and combine them downstream.

```
kitlib echo shoreA*.wav --send --name shore_a
kitlib echo shoreB*.wav --send --name shore_b
```

## What to expect outdoors

Open water in front and rock behind gives a handful of discrete echoes and
almost no diffuse tail. That is excellent for measuring distances and
disappointing if you wanted reverb. The ranging is the stronger result.

Wind is the thing that ruins it, and it ruins it in two ways at once: broadband
noise on the microphone, and the moving air that makes captures disagree. Both
push the confidence down, correctly.

## In your own code

```python
from kitlib import echo

sw = echo.sweep(seconds=10)
echo.write_wav("sweep.wav", sw.signal)

survey = echo.Survey(celsius=4.0)
for path in captures:
    recording, rate = echo.read_wav(path)
    survey.add(echo.reflections(echo.deconvolve(recording, sw), rate))

print(survey.confidence)
for estimate in survey.estimates():
    print(estimate.distance, "±", estimate.spread)

survey.publish(bus, name="lake")
```

Needs `pip install -e ".[echo]"`, which is NumPy and nothing else.

Recorder files are read directly, including the 24-bit ones field recorders
write by default. Audio stays out of this repository on purpose, so keep
captures beside it rather than in it.
