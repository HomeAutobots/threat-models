import { Container, Text, Title } from '@mantine/core'

export function SignedOut() {
  return (
    <Container size="sm" py="xl">
      <Title order={1}>Signed out</Title>
      <Text mt="md">
        Open the sign-in link shown in the Terminal window that started the app. If that window is
        closed, start the app again for a new link.
      </Text>
    </Container>
  )
}
