#pragma once

#include <algorithm>
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
    return now >= next_poll_at_ && !waiting_for_quota(now) && available_credit(now) >= REQUEST_CREDIT_MS;
  }

  bool record_attempt(uint64_t now) {
    if (!ready(now)) return false;
    credit_ms_ = available_credit(now) - REQUEST_CREDIT_MS;
    credit_at_ = now;
    next_poll_at_ = now + ACTIVE_INTERVAL_MS;
    return true;
  }

  void finish(uint64_t now, bool has_flights) {
    next_poll_at_ = std::max(next_poll_at_, now + (has_flights ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS));
  }

  void rate_limited(uint64_t now, std::string_view retry_after) {
    constexpr uint64_t DAY_MS = 86'400'000;
    uint32_t seconds = 0;
    uint64_t wait_ms = DAY_MS;
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
  static constexpr uint64_t ACTIVE_INTERVAL_MS = 60'000;
  static constexpr uint64_t IDLE_INTERVAL_MS = 300'000;
  // One request refills every three minutes, with up to 12 saved for a burst.
  // That bounds one board to 492 requests in any 24 hours.
  static constexpr uint64_t REQUEST_CREDIT_MS = 180'000;
  static constexpr uint64_t MAX_CREDIT_MS = 12 * REQUEST_CREDIT_MS;

  uint64_t available_credit(uint64_t now) const {
    return std::min(MAX_CREDIT_MS, credit_ms_ + (now - std::min(now, credit_at_)));
  }

  uint64_t credit_ms_ = MAX_CREDIT_MS;
  uint64_t credit_at_ = 0;
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

  bool operator<(const Aircraft &other) const {
    return std::tie(position.distance_nm, callsign, type) <
           std::tie(other.position.distance_nm, other.callsign, other.type);
  }
};

}  // namespace overhead
