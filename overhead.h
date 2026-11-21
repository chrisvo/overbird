#pragma once

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <tuple>
#include <vector>

namespace overhead {

enum class View { RADAR, SPOTLIGHT, CARDS, COUNT };

constexpr View step_view(View view, int direction) {
  constexpr int count = static_cast<int>(View::COUNT);
  return static_cast<View>((static_cast<int>(view) + direction + count) % count);
}

class PollSchedule {
 public:
  bool ready(uint64_t now) const {
    return now >= next_poll_at_ && !waiting_for_quota(now);
  }

  bool record_attempt(uint64_t now) {
    if (!ready(now)) return false;
    next_poll_at_ = now + POLL_INTERVAL_MS;
    return true;
  }

  void back_off(uint64_t now, bool client_error = false) {
    next_poll_at_ = std::max(next_poll_at_, now + (client_error ? 300'000 : 30'000));
  }

  void rate_limited(uint64_t now, std::string_view retry_after) {
    uint32_t seconds = 0;
    uint64_t wait_ms = 60'000;
    if (!retry_after.empty()) {
      const char *end = retry_after.data() + retry_after.size();
      const auto result = std::from_chars(retry_after.data(), end, seconds);
      if (result.ec == std::errc{} && result.ptr == end) {
        wait_ms = uint64_t{seconds} * 1000;
      }
    }
    retry_at_ = now + wait_ms;
  }

  bool waiting_for_quota(uint64_t now) const { return now < retry_at_; }

 private:
  static constexpr uint64_t POLL_INTERVAL_MS = 10'000;
  uint64_t next_poll_at_ = 0;
  uint64_t retry_at_ = 0;
};

constexpr double RADIANS_PER_DEGREE = 0.017453292519943295;

inline std::string_view airline_for(std::string_view callsign) {
  if (callsign.size() < 4 || callsign[3] < '0' || callsign[3] > '9') return {};
  for (char character : callsign.substr(4)) {
    if (!(character >= '0' && character <= '9') && !(character >= 'A' && character <= 'Z')) return {};
  }
  static constexpr std::pair<std::string_view, std::string_view> airlines[] = {
      {"AAL", "American"},    {"AAY", "Allegiant"},   {"ACA", "Air Canada"},    {"AFR", "Air France"},
      {"ASA", "Alaska"},      {"BAW", "British Airways"}, {"DAL", "Delta"},    {"DLH", "Lufthansa"},
      {"FDX", "FedEx"},       {"FFT", "Frontier"},    {"HAL", "Hawaiian"},      {"JAL", "Japan Airlines"},
      {"JBU", "JetBlue"},     {"KAL", "Korean Air"},  {"KLM", "KLM"},           {"NKS", "Spirit"},
      {"QFA", "Qantas"},      {"QTR", "Qatar Airways"}, {"SCX", "Sun Country"}, {"SKW", "SkyWest"},
      {"SWA", "Southwest"},   {"UAL", "United"},      {"UPS", "UPS"},           {"VOI", "Volaris"},
      {"WJA", "WestJet"},
  };
  const auto prefix = callsign.substr(0, 3);
  for (const auto &[designator, name] : airlines) {
    if (prefix == designator) return name;
  }
  return {};
}

struct Position {
  double distance_nm;
  double bearing_radians;
};

inline Position relative_position(double home_lat, double home_lon, double latitude, double longitude) {
  const double lat1 = home_lat * RADIANS_PER_DEGREE;
  const double lat2 = latitude * RADIANS_PER_DEGREE;
  const double delta_lon = (longitude - home_lon) * RADIANS_PER_DEGREE;
  const double sin_lat = std::sin((lat2 - lat1) / 2);
  const double sin_lon = std::sin(delta_lon / 2);
  const double a = sin_lat * sin_lat + std::cos(lat1) * std::cos(lat2) * sin_lon * sin_lon;
  return {
      6880.13 * std::asin(std::sqrt(std::clamp(a, 0.0, 1.0))),
      std::atan2(std::sin(delta_lon) * std::cos(lat2),
                 std::cos(lat1) * std::sin(lat2) - std::sin(lat1) * std::cos(lat2) * std::cos(delta_lon)),
  };
}

struct Aircraft {
  Position position;
  std::string callsign;
  std::string type;
  std::optional<int> altitude_ft;
  std::optional<long> speed_kt;
  std::optional<double> ground_track;
  std::string_view airline;
  std::string feed_id{};
  std::array<std::optional<Position>, 2> history{};
  uint32_t history_at_ms = 0;

  bool operator<(const Aircraft &other) const {
    return std::tie(position.distance_nm, callsign, type) <
           std::tie(other.position.distance_nm, other.callsign, other.type);
  }
};

struct FlightSnapshot {
  std::vector<Aircraft> flights;
  std::string updated_at;
  uint32_t received_at_ms = 0;

  bool expired(uint32_t now_ms) const { return now_ms - received_at_ms >= 300'000; }

  void carry_history(const FlightSnapshot &previous) {
    if (previous.expired(received_at_ms)) return;
    for (auto &flight : flights) {
      if (flight.feed_id.empty()) continue;
      const auto same_aircraft = [&](const Aircraft &older) { return older.feed_id == flight.feed_id; };
      const auto older = std::find_if(previous.flights.begin(), previous.flights.end(), same_aircraft);
      if (older == previous.flights.end()) continue;
      // Keep trail points far enough apart to read while updating the marker every ten seconds.
      if (!older->history.front() || previous.received_at_ms - older->history_at_ms >= 30'000) {
        flight.history = {older->position, older->history.front()};
        flight.history_at_ms = previous.received_at_ms;
      } else {
        flight.history = older->history;
        flight.history_at_ms = older->history_at_ms;
      }
    }
  }
};

}  // namespace overhead
