# -*- coding: utf-8 -*-
"""La figure de l'empoisonnement : ce que le mensonge gagne, et le score qui monte.

    python plot_poisoning.py


DEUX PANNEAUX, PAS DEUX AXES : un graphe a deux echelles verticales laisse le
lecteur choisir la lecture qui l'arrange. Ici les deux quantites ne partagent
que l'abscisse, donc la montee du z se lit comme un fait separe.
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

d12 = json.load(open("results-poisoning.json", encoding="utf-8"))["points"]
d24 = json.load(open("results-poisoning-s24.json", encoding="utf-8"))["points"]
pick = lambda d, k: ([p["mensonges"] for p in d if p["verites"] == 1],
                     [p[k] for p in d if p["verites"] == 1])

ENCRE, GRIS, TRAME = "#17171b", "#8e8e99", "#ececf2"
ROUGE, BLEU = "#c0392b", "#2b6cb0"

fig, (h, b) = plt.subplots(2, 1, figsize=(9.4, 7.6), sharex=True,
                           gridspec_kw={"height_ratios": [1.3, 1], "hspace": 0.16})
fig.patch.set_facecolor("white")
for ax in (h, b):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRIS)
    ax.tick_params(colors=GRIS, labelsize=10)
    ax.grid(axis="y", color=TRAME, lw=0.9)
    ax.set_axisbelow(True)
    ax.set_xlim(0, 21.4)

x, y = pick(d12, "mensonge"); x2, y2 = pick(d24, "mensonge")
h.plot(x, y, "-o", color=ROUGE, lw=2.3, ms=7, label="12 seeds", zorder=3)
h.plot(x2, y2, "--s", color=ROUGE, lw=1.6, ms=6, alpha=0.5, label="24 seeds", zorder=2)
h.axhline(0.5, color=GRIS, lw=1, ls=":", zorder=1)
h.text(14.6, 0.525, "coin flip", color=GRIS, fontsize=9.5, va="bottom")
h.set_ylim(-0.05, 1.16)
h.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
h.set_ylabel("share of answers\nthat serve the LIE", color=ENCRE, fontsize=11.5)
h.set_title("One truth. N repetitions of a competing lie.",
            color=ENCRE, fontsize=15.5, weight="bold", loc="left", pad=16)
h.legend(frameon=False, fontsize=10, loc="lower right",
         bbox_to_anchor=(0.99, 0.04), handlelength=2.4)
h.annotate("2 lies: 83% and 88%", xy=(2, 0.833), xytext=(3.6, 0.545),
           color=ENCRE, fontsize=10.5,
           arrowprops=dict(arrowstyle="->", color=ENCRE, lw=1.1))
h.annotate("3 and up: 100%, at both sample sizes", xy=(4, 1.0), xytext=(5.0, 1.075),
           color=ENCRE, fontsize=10.5,
           arrowprops=dict(arrowstyle="->", color=ENCRE, lw=1.1))

x, y = pick(d12, "z_median"); x2, y2 = pick(d24, "z_median")
b.plot(x, y, "-o", color=BLEU, lw=2.3, ms=7, label="12 seeds", zorder=3)
b.plot(x2, y2, "--s", color=BLEU, lw=1.6, ms=6, alpha=0.5, label="24 seeds", zorder=2)
b.axhline(4.0, color=ENCRE, lw=1.3, ls="--", zorder=1)
b.text(0.35, 4.09, "the gate only answers above z = 4",
       color=ENCRE, fontsize=9.5, va="bottom")
b.set_ylim(3.35, 7.75)
b.set_yticks([4, 5, 6, 7])
b.set_xlabel("repetitions of the lie", color=ENCRE, fontsize=11.5)
b.set_ylabel("median confidence\nscore  z", color=ENCRE, fontsize=11.5)
b.legend(frameon=False, fontsize=10, loc="lower right",
         bbox_to_anchor=(0.99, 0.10), handlelength=2.4)
b.annotate("the score RISES with the attack", xy=(10, 6.76), xytext=(2.6, 7.35),
           color=BLEU, fontsize=12, weight="bold",
           arrowprops=dict(arrowstyle="->", color=BLEU, lw=1.5))

fig.text(0.5, 0.045, "On honest data z >= 5 is 355 correct out of 355. "
         "Under this attack z sits at 6 and is wrong every time.",
         ha="center", color=ENCRE, fontsize=11)
fig.text(0.5, 0.014, "holomem / membench   d = 2048   MIT   reproducible offline",
         ha="center", color=GRIS, fontsize=9.5)
fig.subplots_adjust(top=0.915, bottom=0.125, left=0.115, right=0.975)
fig.savefig("figures-5-poisoning.png", dpi=190, facecolor="white")
print("ecrit")
