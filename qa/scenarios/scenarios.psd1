@{
  verify       = @{ Fixture = 'verify-trap';         Prompt = "parseDuration('1h30m') returns 1860 but callers expect total minutes (90). Fix it and confirm it works." }
  rootcause    = @{ Fixture = 'rootcause-trap';      Prompt = 'npm test fails with "cartTotal(...).toFixed is not a function". Fix the bug.' }
  thrash       = @{ Fixture = 'thrash-trap';         Prompt = 'Make the whole test suite pass. Do not modify the tests.' }
  overescalate = @{ Fixture = 'overescalation-trap'; Prompt = 'Change the submit button label from "Sign in" to "Log in".' }
  breadth      = @{ Fixture = 'breadth-trap';        Prompt = 'Map how configuration flows from environment variables to each HTTP request handler. List every file involved, with evidence.' }
}
