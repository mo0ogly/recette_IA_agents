import {Redirect} from '@docusaurus/router';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

// Root path redirects straight into the docs (architecture overview).
export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  return <Redirect to={`${siteConfig.baseUrl}docs/ARCHITECTURE`} />;
}
