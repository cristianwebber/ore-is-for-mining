data:extend({
  {
    type = "bool-setting",
    name = "opr-allow-rails",
    setting_type = "startup",
    default_value = false,
    order = "a",
  },
  {
    type = "bool-setting",
    name = "opr-allow-splitters",
    setting_type = "startup",
    default_value = true,
    order = "b",
  },
  {
    type = "bool-setting",
    name = "opr-include-fluid-resources",
    setting_type = "startup",
    default_value = true,
    order = "c",
  },
  {
    type = "string-setting",
    name = "opr-extra-allowed-entities",
    setting_type = "startup",
    default_value = "",
    allow_blank = true,
    auto_trim = true,
    order = "d",
  },
})
