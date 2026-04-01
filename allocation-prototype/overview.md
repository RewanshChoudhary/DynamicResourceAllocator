
## 1. What The Project Does

This project is a rule-driven delivery allocation system.

Its job is to take:

- a list of customer orders
- a list of delivery partners
- a set of allocation rules

and then decide which partner should receive which order.

The system does not just return a result. It also stores:

- why a partner was accepted or rejected
- how each scoring rule affected the final decision
- a saved record of the decision so it can be replayed and verified later

In simple terms, it is an allocation platform with traceability.

## 2. How It Is Not A Comparison Engine

This project is not a comparison engine because it is not built to compare products, prices, vendors, or services for a user.

A comparison engine normally answers questions like:

- which option is cheaper
- which product is better
- how two services compare side by side

This project does something different.

It makes an operational decision inside a delivery system:

- which delivery partner should be assigned to an order

So the core purpose is decision-making and assignment, not comparison browsing.

Comparison may happen internally at a technical level because the system checks multiple candidate partners, but that is only a step inside allocation. The final goal is assignment, not comparison as a product feature.

## 3. Flow Of The Project

The project flow is:

1. Orders and partners are sent to the API.
2. The active rule configuration is loaded.
3. Hard rules remove partners who should not be considered.
   Examples: unavailable partner, wrong vehicle, low rating, poor vehicle condition, unsafe vehicle for weather.
4. Scoring rules rank the remaining valid partners.
   Examples: proximity, rating, fairness, on-time history, traffic-aware proximity.
5. The best partner is selected in a deterministic way.
6. The allocation result, trace, and manifest are stored.
7. Later, the same decision can be:
   - audited
   - replayed
   - verified
   - simulated under changed rules

## 4. Problem The Project Solves

In delivery systems, assigning orders manually or with unclear logic causes problems such as:

- inconsistent partner selection
- difficulty explaining why one partner was chosen over another
- unfair workload distribution
- unsafe decisions under bad weather or poor vehicle condition
- no reliable way to verify old decisions later

This project solves that by providing:

- clear rule-based allocation
- explainable decisions
- consistent deterministic behavior
- stored evidence for audit and replay
- realistic testing using Zomato-based datasets

## 5. Tech Stack Used

The main tech stack is:

- Python
- FastAPI for the API layer
- Pydantic for request and response validation
- SQLite for storage
- SQLAlchemy for database access
- Alembic for database migrations
- HTML, CSS, and JavaScript for the frontend console

## 6. Testing Library Used

The main testing library used in the project is:

- `pytest`

The project also uses the existing FastAPI and Starlette testing-compatible request flow in unit and integration-style tests.

## 7. Future Plans For The Project

Some realistic future directions for the project are:

- add more production-style business rules
- improve fairness and load balancing logic
- support larger and more varied real-world datasets
- improve the frontend for clearer audit visualization
- add stronger analytics around rejection reasons
- connect the system to live operational inputs instead of only demo payloads
- add role-based views for operators, analysts, and auditors

## 8. Very Small High-Level Architecture Diagram

```text
                +----------------------+
                |   Frontend Console   |
                | HTML / CSS / JS UI   |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |      FastAPI API     |
                | allocation endpoints |
                +----------+-----------+
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
+----------------------+       +----------------------+
|  Rule Configuration  |       | Allocation Pipeline  |
| hard + scoring rules | ----> | filter + score + pick|
+----------------------+       +----------+-----------+
                                          |
                                          v
                             +-------------------------+
                             | SQLite + Manifest Store |
                             | trace, replay, audit    |
                             +-------------------------+
```

## 9. One-Line Summary

This project is an explainable delivery allocation system that assigns orders to partners using rules, stores the reason for each decision, and allows later audit, replay, and simulation.
