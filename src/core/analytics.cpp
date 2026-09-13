#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>

using namespace std;
namespace py = pybind11;

double calc_time_decay_form(const vector<double> &values, const vector<int> &days_ago, double decay_rate) {
    if (values.size() != days_ago.size()) {
        return 0.0;
    }

    double weighted_sum = 0.0;
    double total_weight = 0.0;

    for (size_t i = 0; i < values.size(); ++i) {
        double weight = exp(-decay_rate * days_ago[i]);
        weighted_sum += values[i] * weight;
        total_weight += weight;
    }

    return (total_weight > 0) ? (weighted_sum / total_weight) : 0.0;
}

double calc_consistency(const vector<double> &values) {
    if (values.size() < 2) {
        return 0.0;
    }

    double sum = accumulate(values.begin(), values.end(), 0.0);
    double mean = sum / values.size();

    double sq_sum = 0.0;
    for (double v : values) {
        sq_sum += (v - mean) * (v - mean);
    }

    return sqrt(sq_sum / (values.size() - 1));
}

double calc_composite_rating(double rating, double acs, double kast, double adr) {
    return (rating * 0.40) +
           ((acs / 300.0) * 0.30) +
           ((kast / 100.0) * 0.15) +
           ((adr / 150.0) * 0.15);
}

PYBIND11_MODULE(vct_core, handle) {
    handle.doc() = "VCT Analytics High-Performance Core";

    handle.def("calculate_time_decay_form", &calc_time_decay_form,
               "Calculate weighted average with exponential time decay for player metrics.",
               py::arg("values"), py::arg("days_ago"), py::arg("decay_rate") = 0.05);

    handle.def("calculate_consistency", &calc_consistency,
               "Calculate standard deviation of performance values to measure consistency.",
               py::arg("values"));

    handle.def("calculate_composite_rating", &calc_composite_rating,
               "Calculate a single composite score from multiple player statistics.",
               py::arg("rating"), py::arg("acs"), py::arg("kast"), py::arg("adr"));
}

