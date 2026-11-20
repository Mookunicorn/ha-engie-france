# Engie France – Prix de l'électricité pour Home Assistant

Intégration personnalisée (HACS) qui lit **tes prix** dans l'espace client Engie
(page « Historique des prix de l'électricité ») et les expose en capteurs :
prix du kWh, abonnement, détail par plage (HP/HC, saison haute/basse).
Le site n'est interrogé **une fois par jour** (avec un cache local pour éviter un 2ᵉ appel après un redémarrage).

> Projet non officiel, sans lien avec Engie. Il utilise une API interne non documentée du site :
> elle peut changer sans préavis. À utiliser pour ton propre compte uniquement.

## Installation (HACS)

1. HACS → ⋮ → **Dépôts personnalisés** → colle l'URL de ce dépôt, catégorie **Intégration**.
2. Installe **Engie France – Prix électricité**, redémarre Home Assistant.
3. Paramètres → Appareils et services → **Ajouter une intégration** → *Engie France*.

## Connexion

L'intégration se connecte à ton espace client **avec ton email et ton mot de passe**, comme le fait le navigateur.
Si Engie demande un code (premier appareil, ou appareil non mémorisé), l'assistant te propose de le recevoir
par **SMS ou par email** puis te demande de le saisir.

- La session est conservée sur disque : au quotidien, il n'y a pas de nouvelle connexion tant qu'elle reste valide.
- Si elle expire, l'intégration se reconnecte seule avec ton mot de passe. Si Engie réclame alors un code,
  Home Assistant affiche une demande de **réauthentification** (aucun SMS n'est envoyé sans ton action).
- Si le mot de passe est refusé, l'intégration s'arrête (pour ne pas verrouiller ton compte) et demande de nouveaux identifiants.
- L'email et le mot de passe sont stockés dans la configuration de Home Assistant (**non chiffrée**) : traite ce dossier comme sensible.

## Capteurs

| Capteur | Description |
|---|---|
| Prix du kWh (estimé, saison en cours) | **À utiliser dans le tableau Énergie** (`EUR/kWh`). Fourniture + obligations + acheminement pondéré HP/HC pour la saison en cours (haute : nov.–mars). |
| Prix du kWh (moyenne indicative Engie) | La moyenne annuelle affichée par Engie. |
| Prix du kWh – fourniture / obligations | Composantes fixe / révisable. |
| Prix du kWh – HP/HC × saison haute/basse | Prix complet TTC par plage. |
| Abonnement (an / mois / jour) | Abonnement TTC fourniture + acheminement. |
| Tarif en vigueur depuis | Date d'effet des prix, avec l'offre et la raison en attributs. |

L'**option « part de consommation en heures pleines »** (82 % par défaut) règle le capteur estimé.
Pour la calibrer : prix moyen de ta dernière facture ÷ kWh, comparé aux prix HP/HC de la saison.

Tableau Énergie : *Réseau électrique → Utiliser une entité avec le prix actuel* → `Prix du kWh (estimé…)`.
L'abonnement n'est pas géré par le tableau Énergie.

## Développement

```bash
pip install -r requirements_test.txt
python -m pytest
```

Les tests utilisent une réponse réelle (identifiants de contrat anonymisés) dans `tests/fixtures/`, et un faux serveur
Engie/Okta qui rejoue le parcours de connexion (mot de passe, code, redirections OAuth, session mémorisée).
