export default function AuthLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <div className="min-h-screen flex items-center justify-center bg-[#f7f9f6] text-[#333333]">
            {children}
        </div>
    )
}
