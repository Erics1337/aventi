import { Text } from 'react-native'
import { useTailwind } from 'tailwind-rn'

const MyComponent = () => {
	const tailwind = useTailwind()

	return <Text style={tailwind('text-blue-600')}>Hello world</Text>
}
