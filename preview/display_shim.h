#pragma once

#include <algorithm>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

// The host build records drawing operations made by the firmware lambda.
enum class Color { BLACK, WHITE };
enum class TextAlign { TOP_LEFT, TOP_RIGHT, TOP_CENTER, CENTER, BASELINE_LEFT, BASELINE_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT };
struct Font { const char *name; };

inline std::string json_string(const std::string &value) {
  std::string result = "\"";
  for (unsigned char ch : value) {
    if (ch == '"' || ch == '\\') result += '\\';
    if (ch < 32) {
      char escaped[7];
      std::snprintf(escaped, sizeof(escaped), "\\u%04x", ch);
      result += escaped;
    } else {
      result += ch;
    }
  }
  return result + '"';
}

struct Display {
  bool first = true;
  int get_width() const { return 800; }
  int get_height() const { return 480; }

  void start(const char *kind, Color color) {
    if (!first) std::cout << ',';
    first = false;
    std::cout << "{\"kind\":" << json_string(kind)
              << ",\"color\":" << json_string(color == Color::BLACK ? "black" : "white");
  }

  void print(int x, int y, Font *font, Color color, TextAlign align, const char *value) {
    start("text", color);
    const char *alignment = "TOP_LEFT";
    switch (align) {
      case TextAlign::TOP_RIGHT: alignment = "TOP_RIGHT"; break;
      case TextAlign::TOP_CENTER: alignment = "TOP_CENTER"; break;
      case TextAlign::CENTER: alignment = "CENTER"; break;
      case TextAlign::BASELINE_LEFT: alignment = "BASELINE_LEFT"; break;
      case TextAlign::BASELINE_RIGHT: alignment = "BASELINE_RIGHT"; break;
      case TextAlign::BOTTOM_LEFT: alignment = "BOTTOM_LEFT"; break;
      case TextAlign::BOTTOM_RIGHT: alignment = "BOTTOM_RIGHT"; break;
      default: break;
    }
    std::cout << ",\"x\":" << x << ",\"y\":" << y
              << ",\"font\":" << json_string(font->name)
              << ",\"align\":" << json_string(alignment)
              << ",\"text\":" << json_string(value) << '}';
  }
  void print(int x, int y, Font *font, Color color, const char *value) {
    print(x, y, font, color, TextAlign::TOP_LEFT, value);
  }
  template <typename... Args>
  void printf(int x, int y, Font *font, Color color, TextAlign align, const char *format, Args... args) {
    const int size = std::snprintf(nullptr, 0, format, args...);
    if (size < 0) throw std::runtime_error("Invalid display format");
    std::vector<char> buffer(size + 1);
    std::snprintf(buffer.data(), buffer.size(), format, args...);
    print(x, y, font, color, align, buffer.data());
  }
  template <typename... Args>
  void printf(int x, int y, Font *font, Color color, const char *format, Args... args) {
    printf(x, y, font, color, TextAlign::TOP_LEFT, format, args...);
  }
  void shape(const char *kind, int x, int y, int w, int h, Color color) {
    start(kind, color);
    std::cout << ",\"x\":" << x << ",\"y\":" << y
              << ",\"w\":" << w << ",\"h\":" << h << '}';
  }
  void horizontal_line(int x, int y, int w, Color color) { shape("rectangle", x, y, w, 1, color); }
  void vertical_line(int x, int y, int h, Color color) { shape("rectangle", x, y, 1, h, color); }
  void rectangle(int x, int y, int w, int h, Color color) { shape("rectangle", x, y, w, h, color); }
  void filled_rectangle(int x, int y, int w, int h, Color color) { shape("fill", x, y, w, h, color); }
  void circle(int x, int y, int radius, Color color) { shape("circle", x, y, radius, radius, color); }
  void filled_circle(int x, int y, int radius, Color color) { shape("filled_circle", x, y, radius, radius, color); }
  void fill(Color color) { filled_rectangle(0, 0, get_width(), get_height(), color); }
};
